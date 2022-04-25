from asyncio.log import logger
import json
import time
from msvsbot import init_testing_deploy
import os
from postgrespersistence import PostgresPersistence
from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update, ParseMode, ForceReply
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    CallbackContext,
    MessageHandler,
    Filters,
    PicklePersistence,
)

def main() -> None:
    init_testing_deploy()
    
    TOKEN = os.environ.get('TELE_BOT_TOKEN')
    N = 'msvs-bot'
    DATABASE_URL = os.environ['DATABASE_URL']
    if('postgresql' not in DATABASE_URL):
        DATABASE_URL = DATABASE_URL.replace('postgres','postgresql',1)
        
    pers = PostgresPersistence(url=DATABASE_URL)
    updater = Updater(TOKEN, persistence=pers)
    updater.start_polling()
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    bot = dispatcher.bot
    bot_data = dispatcher.bot_data
    
    logger.info(f'bot data:\n{json.dumps(bot_data)}')
    if('users' in bot_data):
        for user in bot_data['users']: 
            bot.send_message(int(user), f'This is a reminder to book msvs facilities. Use /book to begin.')
    # updater.idle()
    time.sleep(5)
    updater.stop()
    return

if __name__ == '__main__':
    main()