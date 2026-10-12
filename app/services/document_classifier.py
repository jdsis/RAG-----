from __future__ import annotations

from typing import Dict, List

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Linux": ["linux", "ubuntu", "centos", "debian", "bash", "shell", "systemctl", "chmod", "chown", "apt", "yum", "目录结构"],
    "Java": ["java", "jvm", "spring", "mybatis", "maven", "juc", "tomcat", "servlet"],
    "Python": ["python", "fastapi", "flask", "django", "pandas", "numpy", "pip", "爬虫"],
    "前端": ["vue", "react", "javascript", "typescript", "html", "css", "vite", "uni-app"],
    "嵌入式": ["stm32", "单片机", "freertos", "i2c", "spi", "uart", "gpio", "arm"],
    "数据库": ["mysql", "redis", "mongodb", "sql", "索引", "事务", "innodb"],
    "人工智能": ["机器学习", "深度学习", "transformer", "rag", "embedding", "yolo", "opencv", "pytorch"],
    "操作系统": ["进程", "线程", "内存管理", "文件系统", "调度算法"],
    "计算机网络": ["tcp", "http", "dns", "socket", "三次握手", "拥塞控制"],
}


def classify_document(title: str, content: str) -> tuple[str, float, str]:
    sample = f"{title}\n{content[:3000]}".lower()
    scores = {
        name: sum(sample.count(keyword.lower()) for keyword in keywords)
        for name, keywords in CATEGORY_KEYWORDS.items()
    }
    best_name, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0:
        return "未分类", 0.2, "未命中明显技术关键词"
    confidence = min(0.95, 0.55 + best_score * 0.08)
    return best_name, confidence, f"命中 {best_score} 个 {best_name} 相关关键词"
