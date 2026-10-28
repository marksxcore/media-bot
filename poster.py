import os
import re
import random
import time
import requests
import xml.etree.ElementTree as ET
import google.generativeai as genai
from google.generativeai.types import RequestOptions

# Настройка Gemini
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-3.5-flash-lite")

# Список источников
FEEDS = [
    "https://variety.com/feed/",
    "https://www.hollywoodreporter.com/feed/",
    "https://www.rollingstone.com/music/music-news/feed/",
    "https://www.rollingstone.com/culture/feed/",
    "https://www.billboard.com/feed/",
    "https://deadline.com/feed/",
    "https://www.thewrap.com/feed/",
    "https://netinfluencer.com/feed/",
    "https://creatoriq.com/blog/rss.xml",
    "https://www.adweek.com/category/influencer-marketing/feed/",
    "https://lenta.ru/rss/news",
    "https://www.gazeta.ru/export/rss/first.xml",
    "https://aif.ru/rss/culture.php",
    "https://kulturomania.ru/feed/",
    "https://dzen.ru/bloggg/rss",
    "https://dzen.ru/russianteleweek.ru",
    "https://www.comingsoon.net/feed",
    "https://feeds.skynews.com/feeds/rss/entertainment.xml"
]

# Ключевые слова для российских СМИ
CULTURE_KEYWORDS = ["кино", "фильм", "сериал", "музык", "песн", "альбом", "премьер", "трейлер", "режиссер", "актер", "блогер", "тиктокер", "инфлюенсер", "стример", "контент", "звезд", "артист", "шоу", "фестиваль", "концерт"]

# Жесткий фильтр политики
BAD_WORDS = ["ukraine", "war", "politics", "military", "election", "poll", "voter", "president", "government", "украин", "войн", "политик", "спецоперац", "выборы", "явка", "избирател", "президент", "правительств", "госдума"]

def get_news_from_feed(feed_url):
    news_list = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(feed_url, timeout=15, headers=headers)
        root = ET.fromstring(response.content)
        for item in root.findall(".//item"):
            title = item.find("title").text or ""
            desc = item.find("description").text or ""
            link = item.find("link").text or ""
            
            if any(bad in (title + desc).lower() for bad in BAD_WORDS): continue
            if any(domain in feed_url for domain in ["lenta", "gazeta", "aif", "kulturomania", "dzen"]):
                if not any(kw in (title + desc).lower() for kw in CULTURE_KEYWORDS): continue
                
            news_list.append({"title": title, "link": link, "description": desc})
    except Exception:
        pass
    return news_list

def generate_post_text(title, link, description):
    prompt = (
        "Ты — редактор канала 'MEDIA'. Твой стиль: дерзко, коротко, без воды. "
        "Перепиши эту новость на русский язык. Сделай это ОЧЕНЬ КОРОТКО: максимум 3-4 предложения. "
        "Добавь эмодзи (3-5 штук), чтобы текст был живым.\n\n"
        f"Заголовок: {title}\nОписание: {description[:500]}\nСсылка: {link}\n\n"
        "Формат ответа (СТРОГО!):\n"
        "Яркий заголовок с эмодзи.\n"
        "Пустая строка.\n"
        "Текст (2-3 предложения) с эмодзи.\n"
        "Пустая строка.\n"
        "Обязательно оформи ссылку так: '🔗 [Источник](ССЫЛКА)'\n"
        "Хэштеги: 3-4 штуки (через пробел).\n"
    )
    
    for attempt in range(3):
        try:
            response = model.generate_content(prompt, request_options=RequestOptions(timeout=30.0))
            full_text = response.text.strip()
            
            # СТРАХОВКА: Если Gemini оставил голый URL, прячем его в "Источник"
            if "http" in full_text and "[Источник]" not in full_text:
                full_text = re.sub(r"(https?://\S+)", r"🔗 [Источник](\1)", full_text)
                
            return full_text
        except Exception:
            time.sleep(3)
    return None

def send_to_telegram(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    channel_id = os.environ["TELEGRAM_CHANNEL_ID"]
    
    # Конвертация Markdown в HTML
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        # ВКЛЮЧАЕМ ПРЕВЬЮ ССЫЛОК (False)
        payload = {"chat_id": channel_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
        resp = requests.post(url, json=payload, timeout=30)
        
        if resp.status_code == 200:
            print("Пост с превью опубликован!")
        else:
            print(f"Ошибка Telegram: {resp.text}")
    except Exception as e:
        print(f"Сбой отправки: {e}")

if __name__ == "__main__":
    random.shuffle(FEEDS)
    all_news = []
    seen_titles = set()
    
    for feed in FEEDS:
        news_items = get_news_from_feed(feed)
        for news in news_items[:3]:
            if news['title'] not in seen_titles:
                seen_titles.add(news['title'])
                all_news.append(news)
    
    print(f"Найдено новостей: {len(all_news)}")
    
    for index, news in enumerate(all_news):
        post_text = generate_post_text(news['title'], news['link'], news['description'])
        if post_text:
            send_to_telegram(post_text)
            
            # Пауза 30 секунд между постами
            if index < len(all_news) - 1:
                print("Ждем 30 секунд...")
                time.sleep(30)
