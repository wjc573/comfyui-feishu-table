"""
飞书多维表格视频上传节点
用于向飞书多维表格上传视频文件
"""

import json
import re
import requests
import os
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs


class FeishuVideoUploadNode:
    """
    飞书多维表格多媒体上传节点
    
    功能：
    1. 上传视频文件、图片文件或音频文件到飞书云盘
    2. 将文件关联到多维表格的指定列
    3. 支持筛选条件和新建行功能
    4. 支持批量新建行（最多100行）
    5. 视频、图片和音频输入互斥（只能连接其中一个）
    """
    
    def __init__(self):
        self.access_token = None
        self.token_expires_at = 0
        
    @classmethod
    def INPUT_TYPES(s):
        """
        定义节点的输入参数
        """
        return {
            "required": {
                "飞书配置": ("FEISHU_CONFIG",),
                "目标列名": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "必填：目标列名（每行一个）。例：\n附件\n视频文件\n多媒体\n图片文件"
                }),
                "筛选条件": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "可选：行筛选规则（每行一条，支持多种语法）：\n列名+关键词  （仅包含该列包含关键词的行）\n列名-关键词  （排除该列包含关键词的行）\n列名+空值    （仅包含该列为空的行）\n列名-空值    （排除该列为空的行）\n列名+非空值  （仅包含该列非空的行）\n列名-非空值  （排除该列非空的行）\n\n例：\n状态+进行中\n进度-空值"
                })
            },
            "optional": {
                "视频输入": ("VIDEO",),
                "图片输入": ("IMAGE",),
                "音频输入": ("AUDIO",),
                "创建新行": ("BOOLEAN", {
                    "default": False,
                    "label_on": "新建行",
                    "label_off": "更新现有行"
                }),
                "新建行数": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 100,
                    "step": 1,
                    "label": "新建行数"
                })
            }
        }
    
    RETURN_TYPES = ("VIDEO", "IMAGE", "AUDIO", "STRING", "IMAGE")
    RETURN_NAMES = ("视频", "图片", "音频", "状态信息", "使用说明")
    
    FUNCTION = "upload_multimedia_to_table"
    CATEGORY = "飞书工具"
    OUTPUT_NODE = True
    
    def get_access_token(self, app_id: str, app_secret: str) -> Optional[str]:
        """
        获取飞书访问令牌
        """
        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            payload = {
                "app_id": app_id,
                "app_secret": app_secret
            }
            
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if data.get("code") == 0:
                return data.get("tenant_access_token")
            else:
                print(f"获取访问令牌失败: {data.get('msg', '未知错误')}")
                return None
                
        except Exception as e:
            print(f"获取访问令牌时发生错误: {str(e)}")
            return None
    
    def extract_table_info(self, table_url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        从飞书多维表格链接中提取应用ID和表格ID
        """
        try:
            # 飞书多维表格链接格式：
            # https://xxx.feishu.cn/base/xxx/xxx?table=tblxxx&sheet=xxx
            
            # 解析URL参数
            parsed_url = urlparse(table_url)
            query_params = parse_qs(parsed_url.query)
            
            # 从URL参数中获取表格ID
            table_id = query_params.get('table', [None])[0]
            
            # 从URL路径中提取应用ID
            path_parts = parsed_url.path.split('/')
            if len(path_parts) >= 4 and path_parts[1] == 'base':
                url_app_id = path_parts[3]
            elif len(path_parts) >= 3 and path_parts[1] == 'base':
                # 处理 /base/xxx 格式
                url_app_id = path_parts[2]
            else:
                # 尝试旧版本格式
                url_app_id = None
                for i, part in enumerate(path_parts):
                    if part == 'wiki' and i + 1 < len(path_parts):
                        url_app_id = path_parts[i + 1]
                        break
            
            return url_app_id, table_id
            
        except Exception as e:
            print(f"解析表格链接时发生错误: {str(e)}")
            return None, None
    
    def get_table_records(self, access_token: str, app_id: str, table_id: str, max_rows: int = 1000) -> Optional[List[Dict]]:
        """
        获取表格记录
        """
        try:
            url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_id}/tables/{table_id}/records"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            params = {
                "page_size": min(max_rows, 1000),
                "user_id_type": "user_id"
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("items", [])
            else:
                print(f"获取表格记录失败: {data.get('msg', '未知错误')}")
                return None
                
        except Exception as e:
            print(f"获取表格记录时发生错误: {str(e)}")
            return None
    
    def is_empty_value(self, value: Any) -> bool:
        """
        判断值是否为空
        """
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        if isinstance(value, list) and len(value) == 0:
            return True
        if isinstance(value, dict) and len(value) == 0:
            return True
        return False
    
    def value_contains(self, field_val: Any, keyword: str) -> bool:
        """
        检查字段值是否包含关键词
        """
        if field_val is None:
            return False
        
        if isinstance(field_val, list):
            return any(keyword.lower() in str(item).lower() for item in field_val)
        else:
            return keyword.lower() in str(field_val).lower()
    
    def filter_records(self, records: List[Dict], filter_columns: str, filter_condition: str) -> List[Dict]:
        """
        根据条件筛选记录
        """
        if not filter_condition.strip():
            return records
        
        # 解析筛选条件
        conditions = []
        for line in filter_condition.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # 解析条件：列名+关键词 或 列名-关键词
            if line.startswith('+'):
                # 包含条件
                parts = line[1:].split('+', 1)
                if len(parts) == 2:
                    col, val = parts[0].strip(), parts[1].strip()
                    conditions.append(('include', col, val))
            elif line.startswith('-'):
                # 排除条件
                parts = line[1:].split('-', 1)
                if len(parts) == 2:
                    col, val = parts[0].strip(), parts[1].strip()
                    conditions.append(('exclude', col, val))
            else:
                # 默认包含条件
                if '+' in line:
                    parts = line.split('+', 1)
                    if len(parts) == 2:
                        col, val = parts[0].strip(), parts[1].strip()
                        conditions.append(('include', col, val))
                elif '-' in line:
                    parts = line.split('-', 1)
                    if len(parts) == 2:
                        col, val = parts[0].strip(), parts[1].strip()
                        conditions.append(('exclude', col, val))
        
        if not conditions:
            return records
        
        # 应用筛选条件
        filtered = []
        for rec in records:
            fields = rec.get("fields", {})
            
            include_ok = True
            exclude_hit = False
            
            # 检查包含条件
            for col, val in [(c, v) for t, c, v in conditions if t == 'include']:
                field_value = fields.get(col, None)
                if val == "空值":
                    if not self.is_empty_value(field_value):
                        include_ok = False
                        break
                elif val == "非空值":
                    if self.is_empty_value(field_value):
                        include_ok = False
                        break
                else:
                    if not self.value_contains(field_value, val):
                        include_ok = False
                        break
            
            # 检查排除条件
            for col, val in [(c, v) for t, c, v in conditions if t == 'exclude']:
                field_value = fields.get(col, None)
                if val == "空值":
                    if self.is_empty_value(field_value):
                        exclude_hit = True
                        break
                elif val == "非空值":
                    if not self.is_empty_value(field_value):
                        exclude_hit = True
                        break
                else:
                    if self.value_contains(field_value, val):
                        exclude_hit = True
                        break
            
            if include_ok and not exclude_hit:
                filtered.append(rec)
        
        return filtered
    
    def upload_video_to_drive(self, access_token: str, video_data: bytes, file_name: str, 
                             parent_type: str, parent_node: str, file_size: int) -> Optional[str]:
        """
        上传视频文件到飞书云盘
        """
        try:
            url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
            
            headers = {
                "Authorization": f"Bearer {access_token}"
            }
            
            # 准备multipart数据
            files = {
                'file': (file_name, video_data, 'video/mp4')  # 默认MP4格式
            }
            
            data = {
                'file_name': file_name,
                'parent_type': parent_type,
                'parent_node': parent_node,
                'size': str(file_size),
                'checksum': '',
                'extra': ''
            }
            
            response = requests.post(url, headers=headers, data=data, files=files, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            if result.get("code") == 0:
                file_token = result.get("data", {}).get("file_token")
                print(f"✅ 视频上传成功，文件令牌: {file_token}")
                return file_token
            else:
                print(f"❌ 视频上传失败: {result.get('msg', '未知错误')}")
                print(f"错误代码: {result.get('code')}")
                return None
                
        except Exception as e:
            print(f"❌ 视频上传过程中发生异常: {str(e)}")
            return None
    
    def upload_image_to_drive(self, access_token: str, image_data: bytes, file_name: str, 
                             parent_type: str, parent_node: str, file_size: int) -> Optional[str]:
        """
        上传图片文件到飞书云盘
        """
        try:
            url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
            
            headers = {
                "Authorization": f"Bearer {access_token}"
            }
            
            # 准备multipart数据
            files = {
                'file': (file_name, image_data, 'image/jpeg')  # 默认JPEG格式
            }
            
            data = {
                'file_name': file_name,
                'parent_type': parent_type,
                'parent_node': parent_node,
                'size': str(file_size),
                'checksum': '',
                'extra': ''
            }
            
            response = requests.post(url, headers=headers, data=data, files=files, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            if result.get("code") == 0:
                file_token = result.get("data", {}).get("file_token")
                print(f"✅ 图片上传成功，文件令牌: {file_token}")
                return file_token
            else:
                print(f"❌ 图片上传失败: {result.get('msg', '未知错误')}")
                print(f"错误代码: {result.get('code')}")
                return None
                
        except Exception as e:
            print(f"❌ 图片上传过程中发生异常: {str(e)}")
            return None
    
    def upload_audio_to_drive(self, access_token: str, audio_data: bytes, file_name: str, 
                             parent_type: str, parent_node: str, file_size: int) -> Optional[str]:
        """
        上传音频文件到飞书云盘
        """
        try:
            url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
            
            headers = {
                "Authorization": f"Bearer {access_token}"
            }
            
            # 根据文件扩展名确定MIME类型
            mime_type = 'audio/mpeg'  # 默认mp3格式
            if file_name.lower().endswith('.wav'):
                mime_type = 'audio/wav'
            elif file_name.lower().endswith('.aac'):
                mime_type = 'audio/aac'
            elif file_name.lower().endswith('.flac'):
                mime_type = 'audio/flac'
            elif file_name.lower().endswith('.ogg'):
                mime_type = 'audio/ogg'
            elif file_name.lower().endswith('.wma'):
                mime_type = 'audio/x-ms-wma'
            elif file_name.lower().endswith('.m4a'):
                mime_type = 'audio/x-m4a'
            
            # 准备multipart数据
            files = {
                'file': (file_name, audio_data, mime_type)
            }
            
            data = {
                'file_name': file_name,
                'parent_type': parent_type,
                'parent_node': parent_node,
                'size': str(file_size),
                'checksum': '',
                'extra': ''
            }
            
            response = requests.post(url, headers=headers, data=data, files=files, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            if result.get("code") == 0:
                file_token = result.get("data", {}).get("file_token")
                print(f"✅ 音频上传成功，文件令牌: {file_token}")
                return file_token
            else:
                print(f"❌ 音频上传失败: {result.get('msg', '未知错误')}")
                print(f"错误代码: {result.get('code')}")
                return None
                
        except Exception as e:
            print(f"❌ 音频上传过程中发生异常: {str(e)}")
            return None
    
    def create_table_record(self, access_token: str, app_id: str, table_id: str, 
                           target_columns: List[str], file_token: str) -> Optional[str]:
        """
        在表格中创建新记录
        """
        try:
            url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_id}/tables/{table_id}/records"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # 构建字段数据
            fields = {}
            for col in target_columns:
                fields[col] = [{"file_token": file_token}]
            
            payload = {
                "fields": fields
            }
            
            print(f"正在创建记录，目标列: {target_columns}")
            print(f"请求URL: {url}")
            print(f"请求载荷: {payload}")
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            print(f"API响应: {result}")
            
            if result.get("code") == 0:
                record_id = result.get("data", {}).get("record_id")
                if record_id:
                    print(f"✅ 记录创建成功，记录ID: {record_id}")
                    return record_id
                else:
                    print(f"⚠️  API返回成功但record_id为空: {result.get('data', {})}")
                    return None
            else:
                print(f"❌ 记录创建失败: {result.get('msg', '未知错误')}")
                print(f"错误代码: {result.get('code')}")
                print(f"完整响应: {result}")
                return None
                
        except Exception as e:
            print(f"❌ 创建记录时发生异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_table_record(self, access_token: str, app_id: str, table_id: str, 
                           record_id: str, target_columns: List[str], file_token: str) -> bool:
        """
        更新表格中的现有记录
        """
        try:
            url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_id}/tables/{table_id}/records/{record_id}"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # 构建字段数据
            fields = {}
            for col in target_columns:
                fields[col] = [{"file_token": file_token}]
            
            payload = {
                "fields": fields
            }
            
            response = requests.put(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if result.get("code") == 0:
                print(f"✅ 记录更新成功，记录ID: {record_id}")
                return True
            else:
                print(f"❌ 记录更新失败: {result.get('msg', '未知错误')}")
                print(f"错误代码: {result.get('code')}")
                return False
                
        except Exception as e:
            print(f"❌ 更新记录时发生异常: {str(e)}")
            return False
    
    def upload_multimedia_to_table(self, 飞书配置: dict, 目标列名: str,
                                  筛选条件: str, 创建新行: bool = False,
                                  新建行数: int = 1, 视频输入: Any = None,
                                  图片输入: Any = None, 音频输入: Any = None) -> Tuple[Any, Any, Any, str, Any]:
        """
        主要的执行方法 - 支持视频和图片上传
        """
        try:
            # 加载使用说明图片
            usage_image = self._load_usage_image()
            
            # 从配置中获取认证信息
            app_id = 飞书配置.get("app_id", "")
            app_secret = 飞书配置.get("app_secret", "")
            table_url = 飞书配置.get("table_url", "")
            url_app_id = 飞书配置.get("url_app_id", "")
            table_id = 飞书配置.get("table_id", "")
            
            # 验证配置
            if not app_id or not app_secret or not table_url:
                return None, None, None, "错误：配置信息不完整，请检查飞书配置节点", usage_image
            
            if not url_app_id or not table_id:
                return None, None, None, "错误：表格链接格式无效，请检查飞书配置节点", usage_image
            
            # 验证输入类型（视频、图片和音频只能连接其中一个）
            connected_count = sum(1 for x in [视频输入, 图片输入, 音频输入] if x is not None)
            if connected_count == 0:
                return None, None, None, "错误：请连接视频、图片或音频输入（只能连接其中一个）", usage_image
            if connected_count > 1:
                return None, None, None, "错误：视频、图片和音频输入不能同时连接，请只连接其中一个", usage_image
            
            # 解析目标列名
            if not 目标列名.strip():
                return None, None, None, "错误：未填写目标列名，请指定要上传文件的列名", usage_image
            
            # 兼容多种分隔符：英文逗号, 中文逗号，顿号、英文/中文分号，以及换行/回车
            parts = re.split(r"[\,\uFF0C\u3001;\uFF1B\n\r]+", 目标列名.strip())
            target_columns_list = [col.strip() for col in parts if col.strip()]
            if not target_columns_list:
                return None, None, None, "错误：解析列名为空，请检查目标列名输入", usage_image
            
            print(f"目标列: {', '.join(target_columns_list)}")
            
            # 1. 获取访问令牌
            print("正在获取飞书访问令牌...")
            access_token = self.get_access_token(app_id, app_secret)
            if not access_token:
                return None, None, None, "错误：无法获取访问令牌，请检查App ID和App Secret", usage_image
            
            print(f"应用ID: {url_app_id}")
            print(f"表格ID: {table_id}")
            
            # 2. 处理输入数据
            file_token = None
            if 视频输入 is not None:
                print("=== 处理视频输入 ===")
                # 处理视频数据
                print("正在处理视频数据...")
                
                # 处理ComfyUI的VIDEO类型输入
                video_data = None
                file_name = 'video.mp4'
                
                # 检查VIDEO类型的结构
                print(f"视频输入类型: {type(视频输入)}")
                print(f"视频输入属性: {dir(视频输入)}")
                
                # 方法1: 检查是否有data属性（最常见的情况）
                if hasattr(视频输入, 'data') and isinstance(视频输入.data, bytes):
                    video_data = 视频输入.data
                    file_name = getattr(视频输入, 'filename', 'video.mp4')
                    if file_name == 'video.mp4' and hasattr(视频输入, 'name'):
                        file_name = 视频输入.name
                    print(f"从data属性读取数据，大小: {len(video_data)} 字节，文件名: {file_name}")
                
                # 方法2: 检查是否有filename属性
                elif hasattr(视频输入, 'filename') and 视频输入.filename:
                    try:
                        file_path = 视频输入.filename
                        print(f"检测到文件路径: {file_path}")
                        if os.path.exists(file_path):
                            with open(file_path, 'rb') as f:
                                video_data = f.read()
                            file_name = os.path.basename(file_path)
                            print(f"从文件路径读取数据，大小: {len(video_data)} 字节")
                        else:
                            print(f"文件路径不存在: {file_path}")
                            # 尝试从相对路径读取
                            if hasattr(视频输入, 'data'):
                                video_data = 视频输入.data
                                file_name = os.path.basename(file_path)
                                print(f"从data属性读取数据，大小: {len(video_data)} 字节")
                    except Exception as e:
                        print(f"从文件路径读取失败: {e}")
                
                # 方法3: 检查是否有read方法
                elif hasattr(视频输入, 'read') and callable(视频输入.read):
                    try:
                        video_data = 视频输入.read()
                        file_name = getattr(视频输入, 'name', 'video.mp4')
                        print(f"从read方法读取数据，大小: {len(video_data)} 字节")
                    except Exception as e:
                        print(f"从read方法读取失败: {e}")
                
                # 方法4: 直接是字节数据
                elif isinstance(视频输入, bytes):
                    video_data = 视频输入
                    file_name = 'video.mp4'
                    print(f"直接使用字节数据，大小: {len(video_data)} 字节")
                
                # 方法5: 是文件路径字符串
                elif isinstance(视频输入, str) and os.path.exists(视频输入):
                    try:
                        with open(视频输入, 'rb') as f:
                            video_data = f.read()
                        file_name = os.path.basename(视频输入)
                        print(f"从字符串路径读取数据，大小: {len(video_data)} 字节")
                    except Exception as e:
                        print(f"从字符串路径读取失败: {e}")
                
                # 方法6: 检查对象的__dict__属性
                elif hasattr(视频输入, '__dict__'):
                    print(f"检查对象属性: {视频输入.__dict__}")
                    for key, value in 视频输入.__dict__.items():
                        if isinstance(value, bytes) and len(value) > 1000:
                            video_data = value
                            file_name = f'video_{key}.mp4'
                            print(f"从属性 {key} 找到视频数据，大小: {len(video_data)} 字节")
                            break
                        elif isinstance(value, str) and os.path.exists(value) and value.endswith(('.mp4', '.avi', '.mov', '.mkv')):
                            try:
                                with open(value, 'rb') as f:
                                    video_data = f.read()
                                file_name = os.path.basename(value)
                                print(f"从属性 {key} 的文件路径读取数据，大小: {len(video_data)} 字节")
                                break
                            except Exception as e:
                                print(f"从属性 {key} 的文件路径读取失败: {e}")
                
                # 方法7: 尝试bytes()转换
                if video_data is None:
                    try:
                        video_data = bytes(视频输入)
                        file_name = 'video.mp4'
                        print(f"通过bytes()转换获得数据，大小: {len(video_data)} 字节")
                    except Exception as e:
                        print(f"bytes()转换失败: {e}")
                
                # 最终检查
                if video_data is None:
                    print("❌ 所有方法都无法获取视频数据")
                    print(f"请检查VIDEO类型输入的结构: {type(视频输入)}")
                    if hasattr(视频输入, '__dict__'):
                        print(f"对象属性: {视频输入.__dict__}")
                    return 视频输入, None, None, "错误：无法处理视频输入数据，请检查VIDEO类型输入", usage_image
                
                file_size = len(video_data)
                print(f"✅ 最终视频文件大小: {file_size} 字节")
                print(f"✅ 最终文件名: {file_name}")
                
                # 验证数据有效性
                if file_size < 100:  # 小于100字节可能是无效数据
                    print(f"⚠️  警告：文件大小过小 ({file_size} 字节)，可能不是有效的视频文件")
                
                # 3. 上传视频到云盘
                print("正在上传视频到飞书云盘...")
                file_token = self.upload_video_to_drive(
                    access_token, video_data, file_name, 
                    "bitable_file", url_app_id, file_size
                )
                
                if not file_token:
                    return 视频输入, None, None, "错误：视频上传失败", usage_image
                
            elif 图片输入 is not None:
                print("=== 处理图片输入 ===")
                # 处理图片数据
                image_data, file_name = self.process_image_data(图片输入)
                if isinstance(image_data, str):  # 返回的是错误信息
                    return None, None, None, image_data, usage_image
                
                file_size = len(image_data)
                
                # 3. 上传图片到云盘
                print("正在上传图片到飞书云盘...")
                file_token = self.upload_image_to_drive(
                    access_token, image_data, file_name, 
                    "bitable_file", url_app_id, file_size
                )
                
                if not file_token:
                    return None, None, None, "错误：图片上传失败", usage_image
            
            elif 音频输入 is not None:
                print("=== 处理音频输入 ===")
                # 处理音频数据
                audio_data, file_name = self.process_audio_data(音频输入)
                if isinstance(audio_data, str):  # 返回的是错误信息
                    return None, None, None, audio_data, usage_image
                
                file_size = len(audio_data)
                
                # 3. 上传音频到云盘
                print("正在上传音频到飞书云盘...")
                file_token = self.upload_audio_to_drive(
                    access_token, audio_data, file_name, 
                    "bitable_file", url_app_id, file_size
                )
                
                if not file_token:
                    return None, None, None, "错误：音频上传失败", usage_image
            
            # 4. 处理表格操作
            if 创建新行:
                # 新建行模式
                print(f"正在创建 {新建行数} 行新记录...")
                success_count = 0
                failed_count = 0
                
                for i in range(新建行数):
                    print(f"正在创建第 {i+1} 行记录...")
                    record_id = self.create_table_record(
                        access_token, url_app_id, table_id, 
                        target_columns_list, file_token
                    )
                    if record_id is not None and str(record_id).strip():
                        success_count += 1
                        print(f"✅ 第 {i+1} 行创建成功，记录ID: {record_id}")
                    else:
                        failed_count += 1
                        print(f"❌ 第 {i+1} 行创建失败")
                
                print(f"创建结果统计：成功 {success_count} 行，失败 {failed_count} 行")
                
                if success_count > 0:
                    status_msg = f"✅ 文件上传完成！成功创建 {success_count} 行新记录"
                    if success_count < 新建行数:
                        status_msg += f"（预期 {新建行数} 行，失败 {failed_count} 行）"
                else:
                    status_msg = "❌ 文件上传成功，但创建记录失败"
                
            else:
                # 更新现有行模式
                if not 筛选条件.strip():
                    return None, None, None, "错误：更新模式需要设置筛选条件", usage_image
                
                print("正在获取现有记录...")
                records = self.get_table_records(access_token, url_app_id, table_id, 1000)
                if records is None:
                    return None, None, None, "错误：无法获取表格数据", usage_image
                
                print(f"获取到 {len(records)} 条记录")
                
                # 筛选记录
                print("正在根据条件筛选记录...")
                filtered_records = self.filter_records(records, 目标列名, 筛选条件)
                print(f"筛选后剩余 {len(filtered_records)} 条记录")
                
                if not filtered_records:
                    return None, None, None, "错误：没有找到符合条件的记录，请检查筛选条件", usage_image
                
                # 更新筛选后的记录
                print("正在更新筛选后的记录...")
                success_count = 0
                for record in filtered_records:
                    record_id = record.get("record_id")
                    if self.update_table_record(access_token, url_app_id, table_id, 
                                             record_id, target_columns_list, file_token):
                        success_count += 1
                
                if success_count > 0:
                    status_msg = f"✅ 文件上传完成！成功更新 {success_count} 条记录"
                else:
                    status_msg = "❌ 文件上传成功，但更新记录失败"
            
            # 返回结果
            if 视频输入 is not None:
                return 视频输入, None, None, status_msg, usage_image
            elif 图片输入 is not None:
                return None, 图片输入, None, status_msg, usage_image
            elif 音频输入 is not None:
                # 直接返回原始音频输入（与视频、图片处理方式一致）
                return None, None, 音频输入, status_msg, usage_image
            else:
                return None, None, None, status_msg, usage_image
            
        except Exception as e:
            error_msg = f"多媒体上传过程中发生异常: {str(e)}"
            print(error_msg)
            # 在异常情况下也要返回使用说明图片
            try:
                usage_image = self._load_usage_image()
            except:
                usage_image = None
            return None, None, None, error_msg, usage_image
    
    def process_image_data(self, image_input: Any) -> Tuple[Optional[bytes], str]:
        """
        处理ComfyUI的IMAGE类型输入
        """
        print("正在处理图片数据...")
        
        # 处理ComfyUI的IMAGE类型输入
        image_data = None
        file_name = 'image.jpg'
        
        # 检查IMAGE类型的结构
        print(f"图片输入类型: {type(image_input)}")
        print(f"图片输入属性: {dir(image_input)}")
        
        # 方法1: 检查是否有data属性
        if hasattr(image_input, 'data') and isinstance(image_input.data, bytes):
            image_data = image_input.data
            file_name = getattr(image_input, 'filename', 'image.jpg')
            if file_name == 'image.jpg' and hasattr(image_input, 'name'):
                file_name = image_input.name
            print(f"从data属性读取图片数据，大小: {len(image_data)} 字节，文件名: {file_name}")
        
        # 方法2: 检查是否有filename属性
        elif hasattr(image_input, 'filename') and image_input.filename:
            try:
                file_path = image_input.filename
                print(f"检测到图片文件路径: {file_path}")
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        image_data = f.read()
                    file_name = os.path.basename(file_path)
                    print(f"从文件路径读取图片数据，大小: {len(image_data)} 字节")
                else:
                    print(f"图片文件路径不存在: {file_path}")
                    # 尝试从相对路径读取
                    if hasattr(image_input, 'data'):
                        image_data = image_input.data
                        file_name = os.path.basename(file_path)
                        print(f"从data属性读取图片数据，大小: {len(image_data)} 字节")
            except Exception as e:
                print(f"从文件路径读取图片失败: {e}")
        
        # 方法3: 检查是否有read方法
        elif hasattr(image_input, 'read') and callable(image_input.read):
            try:
                image_data = image_input.read()
                file_name = getattr(image_input, 'name', 'image.jpg')
                print(f"从read方法读取图片数据，大小: {len(image_data)} 字节")
            except Exception as e:
                print(f"从read方法读取图片失败: {e}")
        
        # 方法4: 直接是字节数据
        elif isinstance(image_input, bytes):
            image_data = image_input
            file_name = 'image.jpg'
            print(f"直接使用图片字节数据，大小: {len(image_data)} 字节")
        
        # 方法5: 是文件路径字符串
        elif isinstance(image_input, str) and os.path.exists(image_input):
            try:
                with open(image_input, 'rb') as f:
                    image_data = f.read()
                file_name = os.path.basename(image_input)
                print(f"从字符串路径读取图片数据，大小: {len(image_data)} 字节")
            except Exception as e:
                print(f"从字符串路径读取图片失败: {e}")
        
        # 方法6: 处理torch.Tensor (ComfyUI的IMAGE类型)
        elif hasattr(image_input, 'numpy') and callable(image_input.numpy):
            try:
                print("检测到torch.Tensor类型，正在转换为图片...")
                import torch
                import numpy as np
                from PIL import Image
                
                # 将tensor转换为numpy数组
                if hasattr(image_input, 'is_cuda') and image_input.is_cuda:
                    image_input = image_input.cpu()
                
                # 转换为numpy数组
                if hasattr(image_input, 'numpy'):
                    image_array = image_input.numpy()
                else:
                    image_array = image_input.detach().numpy()
                
                print(f"Tensor形状: {image_array.shape}")
                print(f"Tensor数据类型: {image_array.dtype}")
                
                # 处理不同的tensor形状
                if len(image_array.shape) == 4:  # (batch, height, width, channels)
                    # 取第一个图片
                    image_array = image_array[0]
                elif len(image_array.shape) == 3:  # (height, width, channels)
                    # 直接使用
                    pass
                elif len(image_array.shape) == 2:  # (height, width) - 灰度图
                    # 转换为3通道
                    image_array = np.stack([image_array] * 3, axis=-1)
                else:
                    print(f"❌ 不支持的tensor形状: {image_array.shape}")
                    return None, "错误：不支持的tensor形状"
                
                # 确保是3通道RGB
                if image_array.shape[-1] == 4:  # RGBA
                    # 转换为RGB
                    image_array = image_array[:, :, :3]
                elif image_array.shape[-1] == 1:  # 单通道
                    # 转换为3通道
                    image_array = np.stack([image_array[:, :, 0]] * 3, axis=-1)
                
                # 确保值在0-255范围内
                if image_array.dtype == np.float32 or image_array.dtype == np.float64:
                    if image_array.max() <= 1.0:
                        image_array = (image_array * 255).astype(np.uint8)
                    else:
                        image_array = image_array.astype(np.uint8)
                elif image_array.dtype != np.uint8:
                    image_array = image_array.astype(np.uint8)
                
                print(f"处理后的数组形状: {image_array.shape}")
                print(f"处理后的数组数据类型: {image_array.dtype}")
                print(f"值范围: {image_array.min()} - {image_array.max()}")
                
                # 转换为PIL Image
                pil_image = Image.fromarray(image_array)
                
                # 转换为JPEG字节数据
                import io
                buffer = io.BytesIO()
                pil_image.save(buffer, format='JPEG', quality=95)
                image_data = buffer.getvalue()
                buffer.close()
                
                file_name = 'comfyui_image.jpg'
                print(f"✅ 成功从torch.Tensor转换图片，大小: {len(image_data)} 字节")
                
            except Exception as e:
                print(f"❌ 处理torch.Tensor失败: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # 方法7: 检查对象的__dict__属性
        elif hasattr(image_input, '__dict__'):
            print(f"检查图片对象属性: {image_input.__dict__}")
            for key, value in image_input.__dict__.items():
                if isinstance(value, bytes) and len(value) > 100:
                    image_data = value
                    file_name = f'image_{key}.jpg'
                    print(f"从属性 {key} 找到图片数据，大小: {len(image_data)} 字节")
                    break
                elif isinstance(value, str) and os.path.exists(value) and value.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif')):
                    try:
                        with open(value, 'rb') as f:
                            image_data = f.read()
                        file_name = os.path.basename(value)
                        print(f"从属性 {key} 的文件路径读取图片数据，大小: {len(image_data)} 字节")
                        break
                    except Exception as e:
                        print(f"从属性 {key} 的文件路径读取图片失败: {e}")
        
        # 方法8: 尝试bytes()转换
        if image_data is None:
            try:
                image_data = bytes(image_input)
                file_name = 'image.jpg'
                print(f"通过bytes()转换获得图片数据，大小: {len(image_data)} 字节")
            except Exception as e:
                print(f"bytes()转换失败: {e}")
        
        # 最终检查
        if image_data is None:
            print("❌ 所有方法都无法获取图片数据")
            print(f"请检查IMAGE类型输入的结构: {type(image_input)}")
            if hasattr(image_input, '__dict__'):
                print(f"对象属性: {image_input.__dict__}")
            return None, "错误：无法处理图片输入数据，请检查IMAGE类型输入"
        
        file_size = len(image_data)
        print(f"✅ 最终图片文件大小: {file_size} 字节")
        print(f"✅ 最终文件名: {file_name}")
        
        # 验证数据有效性
        if file_size < 50:  # 小于50字节可能是无效数据
            print(f"⚠️  警告：文件大小过小 ({file_size} 字节)，可能不是有效的图片文件")
        
        return image_data, file_name

    def process_audio_data(self, audio_input: Any) -> Tuple[Optional[bytes], str]:
        """
        处理ComfyUI的AUDIO类型输入
        ComfyUI的AUDIO格式是: {"waveform": tensor, "sample_rate": int}
        """
        print("正在处理音频数据...")
        
        # 处理ComfyUI的AUDIO类型输入
        audio_data = None
        file_name = 'audio.wav'
        
        # 检查AUDIO类型的结构
        print(f"音频输入类型: {type(audio_input)}")
        
        # 方法0: ComfyUI标准AUDIO格式 {"waveform": tensor, "sample_rate": int}
        if isinstance(audio_input, dict) and "waveform" in audio_input and "sample_rate" in audio_input:
            try:
                print("检测到ComfyUI标准AUDIO格式")
                waveform = audio_input["waveform"]
                sample_rate = audio_input["sample_rate"]
                
                # 将tensor转换为numpy数组
                if hasattr(waveform, 'cpu'):
                    waveform = waveform.cpu()
                if hasattr(waveform, 'detach'):
                    waveform = waveform.detach()
                waveform_np = waveform.numpy()
                
                # 处理形状: (batch, channels, samples) 或 (batch, samples)
                print(f"波形形状: {waveform_np.shape}")
                
                # 取第一个batch
                if waveform_np.ndim >= 2:
                    waveform_np = waveform_np[0]
                
                # 如果是单通道，确保形状正确
                if waveform_np.ndim == 1:
                    waveform_np = waveform_np[np.newaxis, :]
                
                # 转换为int16格式
                waveform_int16 = (waveform_np * 32767).astype(np.int16)
                
                # 写入WAV文件（使用BytesIO）
                import io
                buffer = io.BytesIO()
                
                # 写入WAV头和数据
                num_channels = waveform_int16.shape[0]
                num_samples = waveform_int16.shape[1]
                byte_rate = sample_rate * num_channels * 2  # 16-bit
                
                # WAV文件头
                header = b'RIFF'
                header += (36 + num_samples * num_channels * 2).to_bytes(4, 'little')
                header += b'WAVEfmt '
                header += (16).to_bytes(4, 'little')  # PCM format
                header += (1).to_bytes(2, 'little')   # Format tag
                header += num_channels.to_bytes(2, 'little')
                header += sample_rate.to_bytes(4, 'little')
                header += byte_rate.to_bytes(4, 'little')
                header += (num_channels * 2).to_bytes(2, 'little')  # Block align
                header += (16).to_bytes(2, 'little')  # Bits per sample
                header += b'data'
                header += (num_samples * num_channels * 2).to_bytes(4, 'little')
                
                # 写入数据
                buffer.write(header)
                
                # 交错写入多通道数据
                for i in range(num_samples):
                    for ch in range(num_channels):
                        buffer.write(waveform_int16[ch, i].tobytes())
                
                audio_data = buffer.getvalue()
                buffer.close()
                
                file_name = 'comfyui_audio.wav'
                print(f"✅ 成功从ComfyUI AUDIO格式转换，大小: {len(audio_data)} 字节")
                
            except Exception as e:
                print(f"❌ 处理ComfyUI AUDIO格式失败: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # 方法1: 检查是否有data属性
        if audio_data is None and hasattr(audio_input, 'data') and isinstance(audio_input.data, bytes):
            audio_data = audio_input.data
            file_name = getattr(audio_input, 'filename', 'audio.mp3')
            if file_name == 'audio.mp3' and hasattr(audio_input, 'name'):
                file_name = audio_input.name
            print(f"从data属性读取音频数据，大小: {len(audio_data)} 字节，文件名: {file_name}")
        
        # 方法2: 检查是否有filename属性
        elif audio_data is None and hasattr(audio_input, 'filename') and audio_input.filename:
            try:
                file_path = audio_input.filename
                print(f"检测到音频文件路径: {file_path}")
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        audio_data = f.read()
                    file_name = os.path.basename(file_path)
                    print(f"从文件路径读取音频数据，大小: {len(audio_data)} 字节")
                else:
                    print(f"音频文件路径不存在: {file_path}")
                    if hasattr(audio_input, 'data'):
                        audio_data = audio_input.data
                        file_name = os.path.basename(file_path)
                        print(f"从data属性读取音频数据，大小: {len(audio_data)} 字节")
            except Exception as e:
                print(f"从文件路径读取音频失败: {e}")
        
        # 方法3: 检查是否有read方法
        elif audio_data is None and hasattr(audio_input, 'read') and callable(audio_input.read):
            try:
                audio_data = audio_input.read()
                file_name = getattr(audio_input, 'name', 'audio.mp3')
                print(f"从read方法读取音频数据，大小: {len(audio_data)} 字节")
            except Exception as e:
                print(f"从read方法读取音频失败: {e}")
        
        # 方法4: 直接是字节数据
        elif audio_data is None and isinstance(audio_input, bytes):
            audio_data = audio_input
            file_name = 'audio.mp3'
            print(f"直接使用音频字节数据，大小: {len(audio_data)} 字节")
        
        # 方法5: 是文件路径字符串
        elif audio_data is None and isinstance(audio_input, str) and os.path.exists(audio_input):
            try:
                with open(audio_input, 'rb') as f:
                    audio_data = f.read()
                file_name = os.path.basename(audio_input)
                print(f"从字符串路径读取音频数据，大小: {len(audio_data)} 字节")
            except Exception as e:
                print(f"从字符串路径读取音频失败: {e}")
        
        # 方法6: 检查对象的__dict__属性
        elif audio_data is None and hasattr(audio_input, '__dict__'):
            print(f"检查音频对象属性: {audio_input.__dict__}")
            for key, value in audio_input.__dict__.items():
                if isinstance(value, bytes) and len(value) > 100:
                    audio_data = value
                    # 根据key推断文件扩展名
                    if 'wav' in key.lower():
                        file_name = f'audio_{key}.wav'
                    elif 'mp3' in key.lower():
                        file_name = f'audio_{key}.mp3'
                    elif 'aac' in key.lower():
                        file_name = f'audio_{key}.aac'
                    else:
                        file_name = f'audio_{key}.mp3'
                    print(f"从属性 {key} 找到音频数据，大小: {len(audio_data)} 字节")
                    break
                elif isinstance(value, str) and os.path.exists(value) and value.lower().endswith(('.mp3', '.wav', '.aac', '.flac', '.ogg', '.wma', '.m4a')):
                    try:
                        with open(value, 'rb') as f:
                            audio_data = f.read()
                        file_name = os.path.basename(value)
                        print(f"从属性 {key} 的文件路径读取音频数据，大小: {len(audio_data)} 字节")
                        break
                    except Exception as e:
                        print(f"从属性 {key} 的文件路径读取音频失败: {e}")
        
        # 方法7: 尝试bytes()转换
        if audio_data is None:
            try:
                audio_data = bytes(audio_input)
                file_name = 'audio.mp3'
                print(f"通过bytes()转换获得音频数据，大小: {len(audio_data)} 字节")
            except Exception as e:
                print(f"bytes()转换失败: {e}")
        
        # 最终检查
        if audio_data is None:
            print("❌ 所有方法都无法获取音频数据")
            print(f"请检查AUDIO类型输入的结构: {type(audio_input)}")
            if hasattr(audio_input, '__dict__'):
                print(f"对象属性: {audio_input.__dict__}")
            return None, "错误：无法处理音频输入数据，请检查AUDIO类型输入"
        
        file_size = len(audio_data)
        print(f"✅ 最终音频文件大小: {file_size} 字节")
        print(f"✅ 最终文件名: {file_name}")
        
        # 验证数据有效性
        if file_size < 50:  # 小于50字节可能是无效数据
            print(f"⚠️  警告：文件大小过小 ({file_size} 字节)，可能不是有效的音频文件")
        
        return audio_data, file_name

    def _load_usage_image(self):
        """加载使用说明图片（从节点目录中加载）"""
        import os
        from PIL import Image
        import torch
        import numpy as np
        
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


# 节点注册映射
NODE_CLASS_MAPPINGS = {
    "FeishuVideoUploadNode": FeishuVideoUploadNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FeishuVideoUploadNode": "上传多媒体（飞书多维表格）",
}