#!/usr/bin/env python3
"""
Generate Traditional Chinese blog posts from NVIDIA Developer Blog
Automatically posts daily, checks for duplicates, uses OpenAI GPT-4
"""

import os
import sys
import json
import feedparser
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from urllib.parse import urljoin, urlparse
import logging

from openai import OpenAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
NVIDIA_BLOG_RSS = "https://developer.nvidia.com/blog/feed/"
NVIDIA_BLOG_URL = "https://developer.nvidia.com/blog/"
CONTENT_DIR = Path("content/posts")
METADATA_FILE = Path(".github/nvidia_blog_metadata.json")
OPENAI_MODEL = "gpt-4-turbo"

class NvidiaBlgoFetcher:
    """Fetch articles from NVIDIA developer blog"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def fetch_latest_article(self) -> Optional[Dict]:
        """Fetch the latest article from NVIDIA blog RSS"""
        try:
            logger.info("Fetching NVIDIA blog RSS feed...")
            feed = feedparser.parse(NVIDIA_BLOG_RSS)

            if not feed.entries:
                logger.warning("No articles found in NVIDIA blog RSS")
                return None

            # Get the latest entry
            latest = feed.entries[0]

            article = {
                'title': latest.get('title', 'No Title'),
                'url': latest.get('link', ''),
                'summary': latest.get('summary', ''),
                'published': latest.get('published', ''),
                'tags': [tag.term for tag in latest.get('tags', [])],
                'author': latest.get('author', 'NVIDIA'),
            }

            # Fetch full content
            article['content'] = self._fetch_full_content(article['url'])

            logger.info(f"Fetched article: {article['title']}")
            return article

        except Exception as e:
            logger.error(f"Error fetching NVIDIA blog: {e}")
            return None

    def _fetch_full_content(self, url: str) -> str:
        """Fetch full article content from URL"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract main content (adjust selector based on NVIDIA's structure)
            article_content = soup.find('article') or soup.find('div', class_='post-content')

            if article_content:
                # Remove scripts and styles
                for script in article_content(['script', 'style']):
                    script.decompose()
                return article_content.get_text(separator='\n', strip=True)[:3000]

            return ""
        except Exception as e:
            logger.warning(f"Error fetching full content: {e}")
            return ""

class DuplicateChecker:
    """Check for duplicate posts"""

    @staticmethod
    def load_metadata() -> Dict:
        """Load metadata of previously posted articles"""
        if METADATA_FILE.exists():
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"posted_articles": []}

    @staticmethod
    def save_metadata(metadata: Dict):
        """Save metadata of posted articles"""
        METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    @staticmethod
    def is_duplicate(article_url: str) -> bool:
        """Check if article was already posted"""
        metadata = DuplicateChecker.load_metadata()
        posted_urls = [item['url'] for item in metadata.get('posted_articles', [])]
        return article_url in posted_urls

    @staticmethod
    def record_posted(article: Dict):
        """Record that article was posted"""
        metadata = DuplicateChecker.load_metadata()
        metadata['posted_articles'].append({
            'url': article['url'],
            'title': article['title'],
            'posted_date': datetime.now().isoformat(),
        })
        DuplicateChecker.save_metadata(metadata)

class BlogPostGenerator:
    """Generate Traditional Chinese blog posts using OpenAI"""

    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def generate_from_nvidia_article(self, article: Dict) -> str:
        """Generate Traditional Chinese blog post from NVIDIA article"""

        logger.info("Generating blog post using OpenAI...")

        prompt = self._create_prompt(article)

        try:
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": """你是一個技術博客作者，專門用繁體中文撰寫高質量的技術文章。

你的任務是根據提供的英文技術文章內容，創建一篇結構清晰、內容豐富的繁體中文技術博客文章。

輸出格式必須是 YAML frontmatter + Markdown 內容，結構如下：
---
title: "..." (繁體中文標題)
date: YYYY-MM-DDTHH:MM:SS+08:00
draft: false
authors: ["nvidia-auto"]
categories: ["all", "NVIDIA", "技術"]
tags: [相關標籤]
summary: "簡短摘要"
readTime: "XX min"
---

文章內容（使用 Markdown 格式）

要求：
1. 標題吸引人且準確反映內容
2. 包含簡介、核心概念、實際應用、性能指標等章節
3. 使用代碼塊、表格、圖表等增強可讀性
4. 包含原文來源鏈接
5. 篇幅 1500-2500 字
6. 適當添加中文技術術語解釋"""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=3000,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            raise

    def _create_prompt(self, article: Dict) -> str:
        """Create prompt for OpenAI"""
        return f"""請根據以下 NVIDIA 技術博客文章內容，生成繁體中文技術博客文章。

原文標題: {article['title']}
原文 URL: {article['url']}
發表日期: {article['published']}
作者: {article['author']}
標籤: {', '.join(article.get('tags', []))}

文章摘要:
{article['summary'][:500]}

文章內容（摘錄）:
{article['content'][:2000]}

請生成完整的繁體中文博客文章，包含 YAML frontmatter。
確保內容準確、易讀、適合技術讀者。"""

class FilenameGenerator:
    """Generate blog post filenames"""

    @staticmethod
    def generate_filename(article: Dict) -> str:
        """Generate filename from article title"""
        # Convert title to slug
        title = article['title']
        # Remove special characters
        slug = "".join(c for c in title if c.isalnum() or c.isspace() or c in '-_')
        slug = slug.strip().lower().replace(' ', '-')
        slug = slug[:50]  # Limit length

        # Add nvidia prefix and current date
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"nvidia-{slug}-zh.md"

        return filename

def main():
    """Main execution"""
    try:
        # Check for OpenAI API key
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable not set")
            sys.exit(1)

        logger.info("Starting NVIDIA blog post generation...")

        # Step 1: Fetch latest article
        fetcher = NvidiaBlgoFetcher()
        article = fetcher.fetch_latest_article()

        if not article:
            logger.warning("No article found, exiting")
            sys.exit(0)

        # Step 2: Check for duplicates
        if DuplicateChecker.is_duplicate(article['url']):
            logger.info(f"Article already posted: {article['title']}")
            sys.exit(0)

        # Step 3: Generate blog post
        generator = BlogPostGenerator(api_key)
        blog_content = generator.generate_from_nvidia_article(article)

        # Step 4: Save to file
        filename = FilenameGenerator.generate_filename(article)
        filepath = CONTENT_DIR / filename

        CONTENT_DIR.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(blog_content)

        logger.info(f"Blog post saved: {filepath}")

        # Step 5: Record posted article
        DuplicateChecker.record_posted(article)

        # Step 6: Create commit message file for GitHub Actions
        commit_message = f"""Add NVIDIA blog post: {article['title']}

Automatically generated from NVIDIA Developer Blog
Original URL: {article['url']}
Generated: {datetime.now().isoformat()}

Co-Authored-By: github-actions[bot] <github-actions[bot]@users.noreply.github.com>
"""

        with open('last_commit_message.txt', 'w', encoding='utf-8') as f:
            f.write(commit_message)

        logger.info("✅ Successfully generated and prepared blog post for commit")
        sys.exit(0)

    except Exception as e:
        logger.error(f"❌ Error during blog generation: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
