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
    "https://lenta.ru/rss/news",
    "https://www.gazeta.ru/export/rss/first.xml"
]

# Ключевые слова для российских СМИ (чтобы отсечь политику и взять культуру)
CULTURE_KEYWORDS = [
    "кино", "фильм", "сериал", "музык", "песн", "альбом", "премьер", "трейлер", "режиссер", "актер",
    "блогер", "тиктокер", "инфлюенсер", "стример", "тикток", "ютуб", "инстаграм", "контент", "ролик"
]

def get_news():
    random.shuffle(FEEDS)
    for feed_url in FEEDS:
        try:
            print(f"Проверяем: {feed_url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(feed_url, timeout=15, headers=headers)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            
            for item in root.findall(".//item"):
                title = item.find("title").text or ""
                link = item.find("link").text or ""
                description = item.find("description").text or ""
                
                # Фильтр плохих слов (политика, война)
                bad_words = ["ukraine", "war", "politics", "military", "conflict", "election", "украин", "войн", "политик", "спецоперац"]
                if any(bad in (title + description).lower() for bad in bad_words):
                    continue
                
                # Если источник российский, проверяем на наличие ключевых слов культуры
                if "lenta" in feed_url or "gazeta" in feed_url:
                    if not any(kw in (title + description).lower() for kw in CULTURE_KEYWORDS):
                        continue
                
                return title, link, description
        except Exception as e:
            print(f"Ошибка {feed_url}: {e}")
            continue
    return None, None, None

def generate_post():
    title, link, description = get_news()
    if not title:
        print("Новостей не найдено.")
        return None

    print(f"Новость: {title}")
    
    prompt = (
        "Ты — редактор канала 'MEDIA'. Твой стиль: индустрия без прикрас, без воды. "
        "Перепиши эту новость на русский язык в 2-3 предложениях. "
        "Добавь эмодзи и легкую иронию. В конце добавь ссылку на источник.\n\n"
        f"Заголовок: {title}\nОписание: {description[:500]}\nСсылка: {link}\n\n"
        "Формат: Заголовок с эмодзи, текст, ссылка '🔗 [Источник](URL)', хэштеги #MEDIA."
    )

    try:
        response = model.generate_content(prompt, request_options=RequestOptions(timeout=30.0))
        return response.text
    except Exception as e:
        print(f"Ошибка Gemini: {e}")
        return None

def send_to_telegram(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    channel_id = os.environ["TELEGRAM_CHANNEL_ID"]
    
    # Конвертация Markdown в HTML
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": channel_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    resp = requests.post(url, json=payload, timeout=30)
    
    if resp.status_code == 200:
        print("Пост отправлен!")
    else:
        print(f"Ошибка Telegram: {resp.text}")

if __name__ == "__main__":
    post_text = generate_post()
    if post_text:
        send_to_telegram(post_text)
