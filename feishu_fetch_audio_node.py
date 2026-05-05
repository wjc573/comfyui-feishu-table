"""
飞书多维表格音频获取节点
从指定列（附件字段）中按筛选条件获取音频，并输出为AUDIO。
支持与其它节点一致的筛选语法：列名+关键词 / 列名-关键词 / 列名+非空值 / 列名-空值 / 列名-非空值
"""

from typing import Any, Dict, List, Optional, Tuple
import io
import json
import re
import os
import tempfile
import uuid

import requests
import torch
import av
from urllib.parse import urlparse, parse_qs

# 尝试导入ComfyUI的folder_paths模块
try:
    import folder_paths
except ImportError:
    folder_paths = None


def f32_pcm(wav: torch.Tensor) -> torch.Tensor:
    """Convert audio to float 32 bits PCM format."""
    if wav.dtype.is_floating_point:
        return wav
    elif wav.dtype == torch.int16:
        return wav.float() / (2 ** 15)
    elif wav.dtype == torch.int32:
        return wav.float() / (2 ** 31)
    raise ValueError(f"Unsupported wav dtype: {wav.dtype}")

def load_audio(filepath: str) -> tuple[torch.Tensor, int]:
    """Load audio file and return waveform and sample rate."""
    with av.open(filepath) as af:
        if not af.streams.audio:
            raise ValueError("No audio stream found in the file.")

        stream = af.streams.audio[0]
        sr = stream.codec_context.sample_rate
        n_channels = stream.channels

        frames = []
        length = 0
        for frame in af.decode(streams=stream.index):
            buf = torch.from_numpy(frame.to_ndarray())
            if buf.shape[0] != n_channels:
                buf = buf.view(-1, n_channels).t()

            frames.append(buf)
            length += buf.shape[1]

        if not frames:
            raise ValueError("No audio frames decoded.")

        wav = torch.cat(frames, dim=1)
        wav = f32_pcm(wav)
        return wav, sr


class FeishuFetchAudioNode:
    """飞书多维表格音频获取节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "飞书配置": ("FEISHU_CONFIG",),
                "目标列名": ("STRING", {"default": "音频", "multiline": False}),
                "筛选条件": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "筛选条件（每行一条）：\n列名+关键词 / 列名-关键词 / 列名+非空值 / 列名-空值 / 列名-非空值"
                }),
                "音频索引": ("INT", {
                    "default": 1, 
                    "min": 1, 
                    "max": 64, 
                    "step": 1,
                    "label": "选择第几个音频"
                }),
                "提取列名": ("STRING", {
                    "default": "", 
                    "multiline": True,
                    "placeholder": "要提取的其他列名（每行一个），如：\n音频标题\n状态\n备注\n\n留空则不提取其他内容"
                }),
            },
            "optional": {
                "列分隔符": ("STRING", {
                    "multiline": True,
                    "default": " | ",
                    "placeholder": "自定义列分隔符，默认为 ' | '。例如：\n- 使用逗号：, \n- 使用分号：; \n- 使用制表符：\\t\n- 使用换行：\\n\n- 使用自定义符号：→\n- 使用多个字符：---\n- 留空则使用默认分隔符"
                }),
                "显示预览": ("BOOLEAN", {
                    "default": True,
                    "label_on": "显示预览",
                    "label_off": "隐藏预览"
                })
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("音频", "状态信息", "提取的内容")
    FUNCTION = "fetch_audio"
    CATEGORY = "飞书工具"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # 让节点在每次执行时都刷新
        import time
        return str(time.time())

    # =============== 基础 API ===============
    def get_access_token(self, app_id: str, app_secret: str) -> Optional[str]:
        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            payload = {"app_id": app_id, "app_secret": app_secret}
            print(f"🔑 获取访问令牌: app_id={app_id}, app_secret={app_secret[:10]}...")
            resp = requests.post(url, json=payload, timeout=30)
            print(f"🔑 响应状态: {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            print(f"🔑 响应数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
            if data.get("code") == 0:
                token = data.get("tenant_access_token")
                print(f"🔑 获取到访问令牌: {token[:20]}...")
                return token
            else:
                print(f"🔑 获取访问令牌失败: {data.get('msg', '未知错误')}")
            return None
        except Exception as e:
            print(f"🔑 获取访问令牌异常: {str(e)}")
            import traceback
            traceback.print_exc()
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
        """获取表格记录"""
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
        
        # 如果搜索值和字段值都是数字，使用精确匹配
        try:
            field_num = float(v)
            needle_num = float(needle)
            return field_num == needle_num
        except (ValueError, TypeError):
            pass
        
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

    # =============== 下载音频 ===============
    def _download_audio_by_file_token(self, access_token: str, file_token: str) -> Optional[Tuple[str, bytes]]:
        """按文件token下载音频，返回文件路径和内容"""
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # 方案一：GET /open-apis/drive/v1/files/download?file_token=xxx
        try:
            url1 = "https://open.feishu.cn/open-apis/drive/v1/files/download"
            print(f"  🔍 尝试方案1: {url1}")
            resp = requests.get(url1, headers=headers, params={"file_token": file_token}, timeout=60, allow_redirects=True)
            print(f"  📡 方案1状态: {resp.status_code}")
            if resp.status_code == 200 and resp.content:
                # 从响应头获取文件名
                content_disposition = resp.headers.get('Content-Disposition', '')
                filename = self._extract_filename_from_header(content_disposition) or f"audio_{file_token}.mp3"
                print(f"  ✅ 方案1成功，文件大小: {len(resp.content)} bytes")
                return filename, resp.content
        except Exception as e:
            print(f"  ❌ 方案1异常: {str(e)}")
        
        # 方案二：GET /open-apis/drive/v1/files/{file_token}/download
        try:
            url2 = f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}/download"
            print(f"  🔍 尝试方案2: {url2}")
            resp2 = requests.get(url2, headers=headers, timeout=60, allow_redirects=True)
            print(f"  📡 方案2状态: {resp2.status_code}")
            if resp2.status_code == 200 and resp2.content:
                # 从响应头获取文件名
                content_disposition = resp2.headers.get('Content-Disposition', '')
                filename = self._extract_filename_from_header(content_disposition) or f"audio_{file_token}.mp3"
                print(f"  ✅ 方案2成功，文件大小: {len(resp2.content)} bytes")
                return filename, resp2.content
        except Exception as e:
            print(f"  ❌ 方案2异常: {str(e)}")
        
        # 方案三：GET /open-apis/drive/v1/medias/{file_token}/download
        try:
            url3 = f"https://open.feishu.cn/open-apis/drive/v1/medias/{file_token}/download"
            print(f"  🔍 尝试方案3: {url3}")
            resp3 = requests.get(url3, headers=headers, timeout=60, allow_redirects=True)
            print(f"  📡 方案3状态: {resp3.status_code}")
            if resp3.status_code == 200 and resp3.content:
                # 从响应头获取文件名
                content_disposition = resp3.headers.get('Content-Disposition', '')
                filename = self._extract_filename_from_header(content_disposition) or f"audio_{file_token}.mp3"
                print(f"  ✅ 方案3成功，文件大小: {len(resp3.content)} bytes")
                return filename, resp3.content
        except Exception as e:
            print(f"  ❌ 方案3异常: {str(e)}")
        
        return None

    def _extract_filename_from_header(self, content_disposition: str) -> Optional[str]:
        """从Content-Disposition头中提取文件名"""
        import re
        match = re.search(r'filename="([^"]+)"', content_disposition)
        if match:
            return match.group(1)
        return None

    def _get_tmp_download_urls(self, access_token: str, file_tokens: List[str], table_id: str) -> Dict[str, str]:
        """获取临时下载链接"""
        if not file_tokens:
            return {}
        
        try:
            url = "https://open.feishu.cn/open-apis/drive/v1/medias/batch_get_tmp_download_url"
            
            # 构建请求参数
            params = {
                "file_tokens": ",".join(file_tokens),
                "extra": json.dumps({"bitablePerm": {"tableId": table_id, "rev": 5}})
            }
            
            headers = {"Authorization": f"Bearer {access_token}"}
            
            print(f"📥 获取 {len(file_tokens)} 个文件的临时下载链接...")
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            print(f"📡 临时下载链接请求状态: {response.status_code}")
            print(f"📡 请求URL: {url}")
            print(f"📡 请求参数: {params}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"📡 响应数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
                if data.get("code") == 0:
                    tmp_urls = {}
                    items = data.get("data", {}).get("tmp_download_urls", [])
                    for item in items:
                        file_token = item.get("file_token")
                        tmp_url = item.get("tmp_download_url")
                        if file_token and tmp_url:
                            tmp_urls[file_token] = tmp_url
                            print(f"✅ 获取到 {file_token} 的临时下载链接")
                    return tmp_urls
                else:
                    print(f"❌ 获取临时下载链接失败: {data.get('msg', '未知错误')}")
                    print(f"❌ 错误代码: {data.get('code')}")
            else:
                print(f"❌ 临时下载链接请求失败: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"❌ 错误响应: {json.dumps(error_data, ensure_ascii=False, indent=2)}")
                except:
                    print(f"❌ 原始响应: {response.text[:500]}")
                
        except Exception as e:
            print(f"❌ 获取临时下载链接异常: {str(e)}")
            import traceback
            traceback.print_exc()
            
        return {}

    def _download_audio_by_tmp_url(self, tmp_url: str) -> Optional[Tuple[str, bytes]]:
        """使用临时下载链接下载音频"""
        try:
            response = requests.get(tmp_url, timeout=60, allow_redirects=True)
            
            if response.status_code == 200 and response.content:
                # 从响应头获取文件名
                content_disposition = response.headers.get('Content-Disposition', '')
                filename = self._extract_filename_from_header(content_disposition) or f"audio_{uuid.uuid4().hex[:8]}.mp3"
                print(f"✅ 音频下载成功，文件大小: {len(response.content)} bytes")
                return filename, response.content
            else:
                print(f"❌ 临时链接下载失败，状态码: {response.status_code}")
                
        except Exception as e:
            print(f"❌ 临时链接下载异常: {str(e)}")
            
        return None

    def _gather_audio_tokens(self, records: List[Dict], target_column: str) -> List[Dict]:
        """收集所有音频token和对应的记录信息"""
        result = []
        for rec in records:
            fields = rec.get('fields', {})
            val = fields.get(target_column)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict) and item.get('file_token'):
                        # 检查文件类型是否为音频
                        file_name = item.get('name', '')
                        if self._is_audio_file(file_name):
                            result.append({
                                'file_token': item['file_token'],
                                'file_name': file_name,
                                'record': rec,
                                'fields': fields
                            })
        return result

    def _is_audio_file(self, filename: str) -> bool:
        """判断文件是否为音频文件"""
        audio_extensions = ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.wma', '.m4a']
        return any(filename.lower().endswith(ext) for ext in audio_extensions)

    def _save_audio_to_temp(self, filename: str, content: bytes) -> Optional[str]:
        """保存音频到临时目录"""
        try:
            # 获取临时目录
            if folder_paths is not None:
                temp_dir = folder_paths.get_temp_directory()
            else:
                temp_dir = tempfile.gettempdir()
            
            # 生成唯一的文件名
            unique_filename = f"feishu_audio_{uuid.uuid4().hex[:8]}_{filename}"
            filepath = os.path.join(temp_dir, unique_filename)
            
            # 保存音频文件
            with open(filepath, 'wb') as f:
                f.write(content)
            
            print(f"✅ 音频已保存: {filepath}, 大小: {len(content)} bytes")
            
            return filepath
            
        except Exception as e:
            print(f"❌ 保存音频失败: {str(e)}")
            return None

    def _extract_single_record_content(self, audio_record: Dict, extract_columns: str, column_separator: str = " | ") -> str:
        """提取单条记录的其他列内容，使用与获取文本节点相同的格式"""
        if not extract_columns.strip():
            return ""
        
        # 兼容多种分隔符：英文逗号, 中文逗号，顿号、英文/中文分号，以及换行/回车
        parts = re.split(r"[\,\uFF0C\u3001;\uFF1B\n\r]+", extract_columns.strip())
        column_names = [col.strip() for col in parts if col.strip()]
        if not column_names:
            return ""
        
        fields = audio_record['fields']
        record_index = 1  # 音频节点只处理单条记录，所以索引固定为1
        
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
    def fetch_audio(self, 飞书配置: dict, 目标列名: str, 筛选条件: str,
                     音频索引: int, 提取列名: str = "", 列分隔符: str = " | ", 显示预览: bool = True) -> Tuple[str, str, str]:
        # 从配置中获取认证信息
        app_id = 飞书配置.get("app_id", "")
        app_secret = 飞书配置.get("app_secret", "")
        table_url = 飞书配置.get("table_url", "")
        url_app_id = 飞书配置.get("url_app_id", "")
        table_id = 飞书配置.get("table_id", "")
        
        # 验证配置
        if not app_id or not app_secret or not table_url:
            return {"ui": {}, "result": ("", "错误：配置信息不完整，请检查飞书配置节点", "")}
        
        if not url_app_id or not table_id:
            return {"ui": {}, "result": ("", "错误：表格链接格式无效，请检查飞书配置节点", "")}
        
        # 1. token
        token = self.get_access_token(app_id, app_secret)
        if not token:
            return {"ui": {}, "result": ("", "错误：无法获取访问令牌", "")}
        # 2. 拉取记录并筛选
        records = self.get_table_records(token, url_app_id, table_id)
        if records is None or len(records) == 0:
            return {"ui": {}, "result": ("", "错误：未获取到任何记录", "")}
        filtered = self.filter_records(records, 筛选条件)
        if len(filtered) == 0:
            return {"ui": {}, "result": ("", "错误：筛选条件未匹配到记录", "")}
        # 3. 收集所有音频token和记录信息
        print(f"🔍 筛选后的记录数量: {len(filtered)}")
        all_audio_records = self._gather_audio_tokens(filtered, 目标列名)
        print(f"🔍 找到的音频记录总数: {len(all_audio_records)}")
        if len(all_audio_records) == 0:
            return {"ui": {}, "result": ("", "错误：目标列未找到任何音频附件", "")}
        
        # 4. 选择指定索引的音频
        if 音频索引 > len(all_audio_records):
            return {"ui": {}, "result": ("", f"错误：音频索引 {音频索引} 超出范围，总共只有 {len(all_audio_records)} 个音频", "")}
        
        selected_record = all_audio_records[音频索引 - 1]  # 转换为0基索引
        print(f"🔍 选择第 {音频索引} 个音频，记录ID: {selected_record['record'].get('record_id', '未知')}")
        print(f"🔍 音频文件名: {selected_record['file_name']}")
        
        # 处理自定义分隔符，如果为空则使用默认分隔符
        if 列分隔符 is None or 列分隔符 == "":
            列分隔符 = " | "
        
        # 处理特殊字符转义
        列分隔符 = 列分隔符.replace('\\n', '\n').replace('\\t', '\t')
        
        # 提取其他列内容
        extracted_content = self._extract_single_record_content(selected_record, 提取列名, 列分隔符)
        
        # 5. 获取临时下载链接
        file_token = selected_record['file_token']
        tmp_urls = self._get_tmp_download_urls(token, [file_token], table_id)
        if not tmp_urls:
            print("⚠️ 无法获取临时下载链接，尝试直接下载")
        
        # 6. 下载选中的音频
        audio_data = None
        # 优先使用临时下载链接
        if file_token in tmp_urls:
            audio_data = self._download_audio_by_tmp_url(tmp_urls[file_token])
        
        # 如果临时链接失败，尝试直接下载
        if audio_data is None:
            audio_data = self._download_audio_by_file_token(token, file_token)
        
        if audio_data is None:
            return {"ui": {}, "result": ("", "错误：音频下载失败", extracted_content)}
        
        # 7. 保存音频到临时目录
        filename, content = audio_data
        audio_path = self._save_audio_to_temp(filename, content)
        if audio_path is None:
            return {"ui": {}, "result": ("", "错误：音频保存失败", extracted_content)}
        
        # 8. 加载音频文件并转换为ComfyUI期望的格式
        try:
            waveform, sample_rate = load_audio(audio_path)
            # 构建音频字典格式
            audio = {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}
        except Exception as e:
            print(f"❌ 音频格式转换失败: {str(e)}")
            return {"ui": {}, "result": ("", f"错误：音频格式转换失败: {str(e)}", extracted_content)}
        
        # 9. 根据开关决定是否准备预览信息
        if 显示预览:
            # 音频预览功能可以在后续版本中实现
            pass
        
        return {
            "ui": {}, 
            "result": (audio, f"成功获取第 {音频索引} 个音频，文件: {filename}, 大小: {len(content)} bytes, 采样率: {sample_rate} Hz", extracted_content)
        }


# 注册节点
NODE_CLASS_MAPPINGS = {
    "FeishuFetchAudioNode": FeishuFetchAudioNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FeishuFetchAudioNode": "获取音频（飞书多维表格）"
}
