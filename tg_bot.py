import json
import os
import telegram
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext

# Настройки Telegram
from data import TELEGRAM_TOKEN, ADMIN_GROUP_ID

# Путь к файлу для хранения данных о топиках
DATA_FILE = 'user_topics.json'

# Загрузка данных из файла
def load_user_topics():
    """
    Загружает данные о топиках из файла.
    """
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as file:
            return json.load(file)
    return {}

# Сохранение данных в файл
def save_user_topics(user_topics):
    """
    Сохраняет данные о топиках в файл.
    """
    with open(DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(user_topics, file, ensure_ascii=False, indent=4)

# Словарь для хранения контекста диалогов
user_topics = load_user_topics()

async def create_topic(bot: telegram.Bot, username: str):
    """
    Создаёт новый топик в группе администраторов.
    """
    response = await bot.create_forum_topic(chat_id=ADMIN_GROUP_ID, name=username)
    return response.message_thread_id

async def find_or_create_topic(bot: telegram.Bot, username: str, user_id: int):
    """
    Ищет топик по имени пользователя или создаёт новый, если его нет.
    """
    # Проверяем, есть ли топик в словаре
    if str(user_id) in user_topics:
        return user_topics[str(user_id)]

    # Если топик не найден, создаём новый
    topic_id = await create_topic(bot, username)
    user_topics[str(user_id)] = topic_id
    save_user_topics(user_topics)  # Сохраняем обновлённые данные
    return topic_id

async def forward_to_admin(update: Update, context: CallbackContext):
    """
    Пересылает сообщение от пользователя в соответствующий топик.
    """
    message = update.message

    # Проверяем, что сообщение пришло из личного чата, а не из группы администраторов
    if message.chat.type != "private":
        print("Сообщение не из личного чата, игнорируем.")
        return

    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    # Если топик ещё не создан, находим или создаём его
    if str(user_id) not in user_topics:
        topic_id = await find_or_create_topic(context.bot, username, user_id)
    else:
        topic_id = user_topics[str(user_id)]

    # Обрабатываем различные типы сообщений
    if message.text:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=message.text,
            message_thread_id=topic_id
        )
    elif message.sticker:
        await context.bot.send_sticker(
            chat_id=ADMIN_GROUP_ID,
            sticker=message.sticker.file_id,
            message_thread_id=topic_id
        )
    elif message.photo:
        await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=message.photo[-1].file_id,
            caption=message.caption,
            message_thread_id=topic_id
        )
    elif message.voice:
        await context.bot.send_voice(
            chat_id=ADMIN_GROUP_ID,
            voice=message.voice.file_id,
            caption=message.caption,
            message_thread_id=topic_id
        )
    elif message.video:
        await context.bot.send_video(
            chat_id=ADMIN_GROUP_ID,
            video=message.video.file_id,
            caption=message.caption,
            message_thread_id=topic_id
        )
    elif message.document:
        await context.bot.send_document(
            chat_id=ADMIN_GROUP_ID,
            document=message.document.file_id,
            caption=message.caption,
            message_thread_id=topic_id
        )
    else:
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text="Получено неподдерживаемое сообщение.",
            message_thread_id=topic_id
        )

async def handle_admin_reply(update: Update, context: CallbackContext):
    """
    Обрабатывает ответы администраторов и пересылает их обратно пользователю.
    """
    message = update.message
    reply_to_message = message.reply_to_message

    # Игнорируем сообщения, если они не являются ответами
    if not reply_to_message:
        return

    # Определяем пользователя по message_thread_id
    topic_id = reply_to_message.message_thread_id
    user_id = None

    for uid, tid in user_topics.items():
        if int(tid) == topic_id:
            user_id = int(uid)
            break

    if not user_id:
        print("Пользователь не найден.")
        return

    # Пересылаем ответ администратора пользователю
    if message.text:
        await context.bot.send_message(chat_id=user_id, text=message.text)
    elif message.sticker:
        await context.bot.send_sticker(chat_id=user_id, sticker=message.sticker.file_id)
    elif message.photo:
        await context.bot.send_photo(chat_id=user_id, photo=message.photo[-1].file_id, caption=message.caption)
    elif message.voice:
        await context.bot.send_voice(chat_id=user_id, voice=message.voice.file_id, caption=message.caption)
    elif message.video:
        await context.bot.send_video(chat_id=user_id, video=message.video.file_id, caption=message.caption)
    elif message.document:
        await context.bot.send_document(chat_id=user_id, document=message.document.file_id, caption=message.caption)
    else:
        await context.bot.send_message(chat_id=user_id, text="Получено неподдерживаемое сообщение.")

def main():
    # Создаем и настраиваем бота
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Обработчик всех типов сообщений от пользователей
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, forward_to_admin))

    # Обработчик ответов администраторов в топиках
    application.add_handler(MessageHandler(filters.Chat(chat_id=ADMIN_GROUP_ID) & filters.REPLY, handle_admin_reply))

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()