"""
Clean Hash 算法实现。
计算用于去重的基于内容的哈希。
"""
import hashlib
import re
from typing import List, Optional

from lxml import html
from lxml.html.clean import Cleaner

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class CleanHasher:
    """
    实现 Clean Hash 算法以进行内容去重。
    
    算法流程:
    1. DOM 降噪: 移除脚本、样式、广告等
    2. 特征提取: 提取可见文本和关键属性
    3. 规范化: 属性排序，移除空白
    4. 哈希: 计算规范化内容的 SHA1
    """
    
    def __init__(self):
        settings = get_settings().hasher
        self.strip_tags = settings.strip_tags
        self.extract_attrs = settings.extract_attrs
        self.ad_selectors = settings.ad_selectors
    
    def compute_content_hash(self, html_content: str) -> str:
        """
        计算原始内容哈希 (原始 DOM 的 SHA1)。
        
        Args:
            html_content: 原始 HTML 字符串
            
        Returns:
            SHA1 十六进制摘要
        """
        return hashlib.sha1(html_content.encode("utf-8")).hexdigest()
    
    def compute_clean_hash(self, html_content: str) -> str:
        """
        计算降噪后的清洗内容哈希。
        
        Args:
            html_content: 原始 HTML 字符串
            
        Returns:
            清洗内容的 SHA1 十六进制摘要
        """
        # 步骤 1: 解析 HTML
        try:
            doc = html.fromstring(html_content)
        except Exception as e:
            logger.warning(f"解析 HTML 失败: {e}")
            # 回退到原始哈希
            return self.compute_content_hash(html_content)
        
        # 步骤 2: 移除噪音元素
        doc = self._remove_noise(doc)
        
        # 步骤 3: 提取特征
        features = self._extract_features(doc)
        
        # 步骤 4: 规范化
        normalized = self._normalize(features)
        
        # 步骤 5: 计算哈希
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    
    def _remove_noise(self, doc: html.HtmlElement) -> html.HtmlElement:
        """从 DOM 中移除噪音元素。"""
        # 使用 lxml cleaner 进行基础清理
        cleaner = Cleaner(
            scripts=True,
            javascript=True,
            comments=True,
            style=True,
            inline_style=True,
            meta=True,
            page_structure=False,
            processing_instructions=True,
            remove_unknown_tags=False,
            safe_attrs_only=False,
        )
        doc = cleaner.clean_html(doc)
        
        # 移除配置中指定的额外标签
        for tag in self.strip_tags:
            for element in doc.xpath(f"//{tag}"):
                element.getparent().remove(element)
        
        # 移除广告容器
        for selector in self.ad_selectors:
            try:
                # 将 CSS 选择器转换为 XPath
                xpath = self._css_to_xpath(selector)
                if xpath:
                    for element in doc.xpath(xpath):
                        if element.getparent() is not None:
                            element.getparent().remove(element)
            except Exception as e:
                logger.debug(f"应用选择器 {selector} 失败: {e}")
        
        return doc
    
    def _css_to_xpath(self, css: str) -> Optional[str]:
        """将简单的 CSS 选择器转换为 XPath。"""
        # 处理类选择器: .class
        if css.startswith("."):
            class_name = css[1:]
            return f"//*[contains(@class, '{class_name}')]"
        
        # 处理 ID 选择器: #id
        if css.startswith("#"):
            id_name = css[1:]
            return f"//*[@id='{id_name}']"
        
        # 处理属性包含: [attr*='value']
        match = re.match(r"\[(\w+)\*='([^']+)'\]", css)
        if match:
            attr, value = match.groups()
            return f"//*[contains(@{attr}, '{value}')]"
        
        # 处理简单标签
        if re.match(r"^[a-z]+$", css):
            return f"//{css}"
        
        return None
    
    def _extract_features(self, doc: html.HtmlElement) -> List[str]:
        """提取文本内容和关键属性。"""
        features = []
        
        # 提取可见文本
        text_content = doc.text_content()
        if text_content:
            features.append(("text", text_content.strip()))
        
        # 提取关键属性
        for attr in self.extract_attrs:
            for element in doc.xpath(f"//*[@{attr}]"):
                value = element.get(attr)
                if value:
                    features.append((attr, value.strip()))
        
        return features
    
    def _normalize(self, features: List[tuple]) -> str:
        """规范化提取的特征。"""
        # 按类型然后按值排序
        sorted_features = sorted(features, key=lambda x: (x[0], x[1]))
        
        # 构建规范化字符串
        parts = []
        for feat_type, feat_value in sorted_features:
            # 规范化空白
            normalized_value = re.sub(r"\s+", " ", feat_value).strip()
            if normalized_value:
                parts.append(f"{feat_type}:{normalized_value}")
        
        return "\n".join(parts)
    
    def get_cleaned_dom(self, html_content: str) -> str:
        """
        获取用于存储的清洗后 DOM HTML。
        
        Args:
            html_content: 原始 HTML 字符串
            
        Returns:
            清洗后的 HTML 字符串
        """
        try:
            doc = html.fromstring(html_content)
            doc = self._remove_noise(doc)
            return html.tostring(doc, encoding="unicode", pretty_print=True)
        except Exception as e:
            logger.warning(f"清洗 DOM 失败: {e}")
            return html_content
