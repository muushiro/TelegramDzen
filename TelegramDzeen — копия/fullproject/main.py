import os
import asyncio
import configparser
import getpass
import logging
import requests
import json
import aiocron
from telethon.sync import TelegramClient, events
from telethon.errors import AuthRestartError
from telethon.tl.types import MessageMediaWebPage

# Set the timezone manually
os.environ['TZ'] = 'Europe/Moscow'  # Replace with your timezone

# Читаем конфигурационный файл
config = configparser.ConfigParser()
config.read('config.ini')

# Получаем параметры API
api_id = config.get('Telegram', 'api_id')
api_hash = config.get('Telegram', 'api_hash')
session_name = config.get('Telegram', 'session_name')
channels = config['Channels']['channel_usernames'].split(',')
groq_api_key = config['Groq']['api_key']

# Создаем клиента Telegram
telegram_client = TelegramClient(
    session_name, api_id, api_hash,
    system_version='4.16.30-vxCUSTOM',
    device_model='Wind5',
    app_version='v0.1a'
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Путь к файлу с обработанными сообщениями
processed_messages_file = 'processed_messages.json'

# Читаем уже обработанные сообщения из файла
if os.path.exists(processed_messages_file):
    with open(processed_messages_file, 'r') as file:
        processed_messages = json.load(file)
else:
    processed_messages = {}

# Функция для суммаризации текста через Groq API
def summarize_with_groq(text):
    url = 'https://api.groq.com/summarize'
    headers = {
        'Authorization': f'Bearer {groq_api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'text': text
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        summary = response.json()['summary']
        return summary
    except requests.exceptions.RequestException as e:
        logger.error(f"Error summarizing text: {e}")
        return None

# Функция для добавления водяного знака
def add_watermark(text):
    watermark = "\n\nТелеграмм | Дзен"
    return f"**{text}**{watermark}"

async def parse_channels():
    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()

    new_processed_messages = {}
    for channel in channels:
        channel_entity = await client.get_entity(channel)
        messages = await client.get_messages(channel_entity, limit=10)  # Получаем последние 10 сообщений

        text_posts = []
        new_processed_messages[channel] = []

        for message in messages:
            if message.text and message.id not in processed_messages.get(channel, []):  # Проверяем, есть ли текст в сообщении и не было ли оно обработано ранее
                text_posts.append(message.text)
                new_processed_messages[channel].append(message.id)  # Добавляем ID сообщения в список обработанных

        channel_posts[channel] = text_posts

    # Обновляем файл с обработанными сообщениями
    with open(processed_messages_file, 'w') as file:
        json.dump({**processed_messages, **new_processed_messages}, file)

    print(channel_posts)
    await client.disconnect()

# Планируем выполнение parse_channels каждый день в 09:00
aiocron.crontab('0 9 * * *', func=parse_channels)

# Обработчик новых сообщений в Telegram
@telegram_client.on(events.NewMessage(chats=channels))
async def handle_new_message(event):
    message = event.message
    if message.text:
        original_text = message.text
        summarized_text = summarize_with_groq(original_text)
        logger.info(f"Original text: {original_text}")
        logger.info(f"Summarized text: {summarized_text}")
        formatted_message = add_watermark(summarized_text)
        await telegram_client.send_message(event.chat_id, formatted_message)

# Основная функция для запуска клиента Telegram
async def main():
    try:
        await telegram_client.start(phone=lambda: input('Please enter your phone (or bot token): '),
                                    password=lambda: getpass.getpass('Please enter your 2FA password: '))
        logger.info("Successfully logged in to Telegram")
        await telegram_client.run_until_disconnected()

    except AuthRestartError:
        # Если возникает AuthRestartError, запрашиваем облачный пароль
        try:
            cloud_password = getpass.getpass('Please enter your cloud password: ')
            await telegram_client.start(password=cloud_password)
        except Exception as e:
            logger.error(f"Error during Telegram login with cloud password: {e}")
    except Exception as e:
        logger.error(f"Error during Telegram login or message processing: {e}")

if __name__ == '__main__':
    asyncio.run(main())