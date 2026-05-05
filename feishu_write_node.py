"""
飞书多维表格写入节点
用于将文本写入到飞书多维表格的指定位置
"""

import json
import re
import requests
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs


class FeishuWriteNode:
    """
    飞书多维表格写入节点
    
    功能：
    1. 接收文本输入并写入飞书多维表格
    2. 支持筛选条件定位目标单元格
    3. 支持增加新行并写入指定列
    4. 支持指定目标列名
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
                    "placeholder": "必填：目标列名（每行一个）。例：\n文本\n内容\n备注\n描述"
                }),
                "筛选条件": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "筛选条件（每行一条，支持多种语法）：\n列名+关键词  （仅包含该列包含关键词的行）\n列名-关键词  （排除该列包含关键词的行）\n列名+非空值  （仅包含该列非空的行）\n列名-空值    （排除该列为空的行）\n列名-非空值  （排除该列非空的行）\n\n例：\n进度-完成\n状态+非空值"
                }),
                "增加行": ("BOOLEAN", {
                    "default": False,
                    "label_on": "增加行",
                    "label_off": "写入现有行"
                }),
                "增加行数": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 100,
                    "step": 1,
                    "label": "增加行数"
                }),
                "输入文本": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "要写入表格的文本内容"
                })
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "IMAGE")
    RETURN_NAMES = ("输出文本", "状态信息", "使用说明")
    
    FUNCTION = "write_to_table"
    CATEGORY = "飞书工具"
    
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
            app_id = None
            path_parts = parsed_url.path.split('/')
            if 'base' in path_parts:
                base_index = path_parts.index('base')
                if len(path_parts) > base_index + 1:
                    app_id = path_parts[base_index + 1]
            
            # 从URL参数中获取工作表ID（可选）
            sheet_id = query_params.get('sheet', [None])[0]
            
            print(f"解析结果 - 应用ID: {app_id}, 表格ID: {table_id}, 工作表ID: {sheet_id}")
            
            return app_id, table_id
            
        except Exception as e:
            print(f"解析表格链接时发生错误: {str(e)}")
            return None, None
    
    def get_table_records(self, access_token: str, app_id: str, table_id: str, max_rows: int = 1000) -> Optional[List[Dict]]:
        """
        获取表格记录
        """
        try:
            url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_id}/tables/{table_id}/records"
            params = {
                "page_size": min(max_rows, 100),  # 飞书API单次最多100条
                "page_token": ""
            }
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            all_records = []
            
            while len(all_records) < max_rows:
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                if data.get("code") != 0:
                    print(f"获取表格记录失败: {data.get('msg', '未知错误')}")
                    break
                
                records = data.get("data", {}).get("items", [])
                if not records:
                    break
                
                all_records.extend(records)
                
                # 检查是否有下一页
                page_token = data.get("data", {}).get("page_token")
                if not page_token:
                    break
                    
                params["page_token"] = page_token
                
                # 防止无限循环
                if len(all_records) >= max_rows:
                    break
            
            return all_records[:max_rows]
            
        except Exception as e:
            print(f"获取表格记录时发生错误: {str(e)}")
            return None
    
    def filter_records(self, records: List[Dict], filter_condition: str) -> List[Dict]:
        """
        根据条件筛选记录（支持语法：列名+关键词 / 列名-关键词）
        """
        if not records or not filter_condition.strip():
            return records
        
        # 解析条件语法
        include_conditions: List[Tuple[str, str]] = []
        exclude_conditions: List[Tuple[str, str]] = []
        
        for raw_line in filter_condition.strip().split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            # 优先解析 + / - 语法
            m = re.match(r"^\s*([^+\-=\s]+)\s*([+-])\s*(.+?)\s*$", line)
            if m:
                col = m.group(1).strip()
                op = m.group(2)
                val = m.group(3).strip()
                if op == '+':
                    include_conditions.append((col, val))
                else:
                    exclude_conditions.append((col, val))
                continue
            # 兼容旧格式：列名=值
            if '=' in line:
                col, val = line.split('=', 1)
                include_conditions.append((col.strip(), val.strip()))
        
        def value_contains(field_val: Any, needle: str) -> bool:
            """判断字段值是否包含子串（大小写不敏感）。支持标量/列表。"""
            if field_val is None:
                return False
            
            # 如果搜索值和字段值都是数字，使用精确匹配
            try:
                field_num = float(field_val)
                needle_num = float(needle)
                return field_num == needle_num
            except (ValueError, TypeError):
                pass
            
            needle_l = str(needle).lower()
            if isinstance(field_val, list):
                for v in field_val:
                    if needle_l in str(v).lower():
                        return True
                return False
            return needle_l in str(field_val).lower()
        
        def is_empty_value(field_val: Any) -> bool:
            """判断字段值是否为空"""
            if field_val is None:
                return True
            if isinstance(field_val, str) and not field_val.strip():
                return True
            if isinstance(field_val, list) and len(field_val) == 0:
                return True
            return False
        
        def check_condition(field_val: Any, condition: str) -> bool:
            """检查字段值是否满足条件"""
            if condition == "空值":
                return is_empty_value(field_val)
            elif condition == "非空值":
                return not is_empty_value(field_val)
            else:
                # 普通关键词匹配
                return value_contains(field_val, condition)
        
        filtered: List[Dict] = []
        for rec in records:
            fields = rec.get('fields', {})
            
            # include 判定：若无 include 条件，则视为通过；否则要求全部命中
            include_ok = True
            if include_conditions:
                include_ok = True
                for col, val in include_conditions:
                    # 当字段缺失时，将其视为"空值"
                    field_value = fields.get(col, None)
                    if not check_condition(field_value, val):
                        include_ok = False
                        break
            
            # exclude 判定：任一命中即排除
            # 注意：当字段缺失时将其视为“空值”，以便条件如 列名-空值 能排除该记录
            exclude_hit = False
            for col, val in exclude_conditions:
                field_value = fields.get(col, None)
                if check_condition(field_value, val):
                    exclude_hit = True
                    break
            
            if include_ok and not exclude_hit:
                filtered.append(rec)
        
        return filtered
    
    def update_existing_records(self, access_token: str, app_id: str, table_id: str, 
                               records: List[Dict], target_columns: List[str], input_text: str) -> Tuple[int, str]:
        """
        更新现有记录 - 支持多个目标列
        """
        if not records:
            return 0, "没有找到符合条件的记录"
        
        updated_count = 0
        error_messages = []
        
        for record in records:
            try:
                record_id = record.get("record_id")
                if not record_id:
                    continue
                
                # 构建更新数据 - 支持多个列
                fields_data = {}
                for column in target_columns:
                    fields_data[column] = input_text
                
                update_data = {
                    "fields": fields_data
                }
                
                # 发送更新请求
                url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_id}/tables/{table_id}/records/{record_id}"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                response = requests.put(url, json=update_data, headers=headers, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                if data.get("code") == 0:
                    updated_count += 1
                else:
                    error_messages.append(f"记录 {record_id} 更新失败: {data.get('msg', '未知错误')}")
                    
            except Exception as e:
                error_messages.append(f"记录 {record.get('record_id', 'unknown')} 更新异常: {str(e)}")
        
        status_msg = f"成功更新 {updated_count} 条记录"
        if error_messages:
            status_msg += f"，失败 {len(error_messages)} 条"
            if len(error_messages) <= 3:  # 只显示前3个错误
                status_msg += f"：{'; '.join(error_messages)}"
            else:
                status_msg += f"：{'; '.join(error_messages[:3])}...等"
        
        return updated_count, status_msg
    
    def add_new_rows(self, access_token: str, app_id: str, table_id: str, 
                     target_columns: List[str], input_text: str, rows_to_add: int) -> Tuple[int, str]:
        """
        添加新行 - 支持多个目标列
        """
        added_count = 0
        error_messages = []
        
        for i in range(rows_to_add):
            try:
                # 构建新行数据 - 支持多个列
                fields_data = {}
                for column in target_columns:
                    fields_data[column] = input_text
                
                new_row_data = {
                    "fields": fields_data
                }
                
                # 发送创建请求
                url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_id}/tables/{table_id}/records"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                response = requests.post(url, json=new_row_data, headers=headers, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                if data.get("code") == 0:
                    added_count += 1
                else:
                    error_messages.append(f"第 {i+1} 行创建失败: {data.get('msg', '未知错误')}")
                    
            except Exception as e:
                error_messages.append(f"第 {i+1} 行创建异常: {str(e)}")
        
        status_msg = f"成功添加 {added_count} 行"
        if error_messages:
            status_msg += f"，失败 {len(error_messages)} 行"
            if len(error_messages) <= 3:  # 只显示前3个错误
                status_msg += f"：{'; '.join(error_messages)}"
            else:
                status_msg += f"：{'; '.join(error_messages[:3])}...等"
        
        return added_count, status_msg
    
    def write_to_table(self, 飞书配置: dict, 输入文本: str, 目标列名: str, 
                      筛选条件: str, 增加行: bool, 增加行数: int) -> Tuple[str, str, Any]:
        """
        主要的执行方法
        """
        try:
            # 从配置中获取认证信息
            app_id = 飞书配置.get("app_id", "")
            app_secret = 飞书配置.get("app_secret", "")
            table_url = 飞书配置.get("table_url", "")
            url_app_id = 飞书配置.get("url_app_id", "")
            table_id = 飞书配置.get("table_id", "")
            
            # 验证配置
            if not app_id or not app_secret or not table_url:
                return 输入文本, "错误：配置信息不完整，请检查飞书配置节点"
            
            if not url_app_id or not table_id:
                return 输入文本, "错误：表格链接格式无效，请检查飞书配置节点"
            
            # 检查输入文本
            if not 输入文本.strip():
                return 输入文本, "错误：输入文本为空，无法执行写入操作"
            
            # 解析目标列名（支持多个列名）
            if not 目标列名.strip():
                return 输入文本, "错误：未指定目标列名，请填写要写入的列名"
            
            # 兼容多种分隔符：英文逗号, 中文逗号，顿号、英文/中文分号，以及换行/回车
            parts = re.split(r"[\,\uFF0C\u3001;\uFF1B\n\r]+", 目标列名.strip())
            target_columns_list = [col.strip() for col in parts if col.strip()]
            if not target_columns_list:
                return 输入文本, "错误：解析列名为空，请检查目标列名输入"
            
            print(f"目标列: {', '.join(target_columns_list)}")
            
            # 1. 获取访问令牌
            print("正在获取飞书访问令牌...")
            access_token = self.get_access_token(app_id, app_secret)
            if not access_token:
                return 输入文本, "错误：无法获取访问令牌，请检查App ID和App Secret"
            
            print(f"应用ID: {url_app_id}")
            print(f"表格ID: {table_id}")
            print(f"目标列: {', '.join(target_columns_list)}")
            print(f"操作模式: {'增加行' if 增加行 else '更新现有行'}")
            
            if 增加行:
                # 2. 增加新行
                print(f"正在添加 {增加行数} 行...")
                added_count, status_msg = self.add_new_rows(
                    access_token, url_app_id, table_id, target_columns_list, 输入文本, 增加行数
                )
                
                final_status = f"增加行操作完成。{status_msg}"
                if added_count > 0:
                    final_status += f" 已将文本写入到 {', '.join(target_columns_list)} 列的新行中。"
                
            else:
                # 2. 获取现有记录
                print("正在获取表格记录...")
                records = self.get_table_records(access_token, url_app_id, table_id, 1000)
                if records is None:
                    return 输入文本, "错误：无法获取表格数据"
                
                print(f"获取到 {len(records)} 条记录")
                
                # 3. 应用筛选条件
                if 筛选条件.strip():
                    print("正在应用筛选条件...")
                    original_count = len(records)
                    records = self.filter_records(records, 筛选条件)
                    print(f"筛选后剩余 {len(records)} 条记录")
                    
                    if len(records) == 0:
                        return 输入文本, f"警告：筛选条件过于严格，没有找到符合条件的记录。原始记录数：{original_count}"
                
                # 4. 更新现有记录
                print("正在更新符合条件的记录...")
                updated_count, update_status = self.update_existing_records(
                    access_token, url_app_id, table_id, records, target_columns_list, 输入文本
                )
                
                final_status = f"更新操作完成。{update_status}"
                if updated_count > 0:
                    final_status += f" 已将文本写入到 {', '.join(target_columns_list)} 列的 {updated_count} 个单元格中。"
            
            # 加载使用说明图片
            usage_image = self._load_usage_image()
            
            return 输入文本, final_status, usage_image
            
        except Exception as e:
            error_msg = f"执行过程中发生错误: {str(e)}"
            print(error_msg)
            usage_image = self._load_usage_image()
            return 输入文本, error_msg, usage_image

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
