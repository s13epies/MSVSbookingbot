#!/usr/bin/env python
# pylint: disable=C0116,W0613
# This program is dedicated to the public domain under the CC0 license.

'''
Send /start to initiate the conversation.
Press Ctrl-C on the command line to stop the bot.
'''
import logging
import datetime, dateparser
from runpy import run_module
import html
import json
import traceback
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ParseMode, ForceReply
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
from postgrespersistence import PostgresPersistence
import re
import os

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)


logger = logging.getLogger(__name__)

#static stuff
depots = ['11FMD', '12FMD', '13FMD', '19FMD']
AUTHTYPE, AUTH, DEPOT, RNAME= range(4)   # for registration conversation
NRIC, PHONE = range(2)  # registration authentication type
t_offset = datetime.timedelta(hours=8)  # for date offset from server time
# for error logging
DEVELOPER_CHAT_ID = 291603849
PORT = int(os.environ.get('PORT', 5000))
# Define a few command handlers. These usually take the two arguments update and
# context.
def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    bot = context.bot
    chatid = update.message.chat_id
    bot.send_message(
        chat_id=chatid,
        text=f'Send /register to register user, /deregister to deregister.'
    )

def register(update: Update, context: CallbackContext) -> int:   # Registration start point
    bot = context.bot
    user = update.effective_user
    context.user_data.clear()
    context.user_data['userid'] = user.id   # Collect userid
    if('users' in context.bot_data):
        if(context.bot_data['users'][user.id] is not None): # duplicate user
            update.message.reply_text(text='User already registered!')
            return ConversationHandler.END
    logger.info('Asking user for authentication')
    keyboard = [
        [
            InlineKeyboardButton(f'NRIC', callback_data=0),
            InlineKeyboardButton(f'Phone Number', callback_data=1)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(text=f'Please select user authentication type', reply_markup=reply_markup)
    return AUTHTYPE

def auth(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    auth_type = query.data  # select type of authentication
    context.user_data['auth_type']=auth_type
    auth_prompt = ''
    if(auth_type==NRIC):
        auth_prompt = 'NRIC'
    elif(auth_type==PHONE):
        auth_prompt = 'phone number'
    query.answer()
    bot = context.bot
    bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
        text=f'Please enter the last 4 digits of your {auth_prompt}'
    )
    return AUTH

def depot(update: Update, context: CallbackContext) -> int:
    auth_key = update.message.text
    bot = context.bot
    
    keyboard = [
        [
            InlineKeyboardButton(str(depot), callback_data=str(i)) for i, depot in enumerate(depots)    # Create inlinebuttons for each depot
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data['msgid'],
        text='Please select your depot:', reply_markup=reply_markup
    )
    return DEPOT

def rname(update: Update, context: CallbackContext) -> int: # Same logic, prompt for rank and name
    bot = context.bot
    query = update.callback_query
    depot = query.data
    query.answer()
    context.user_data['depot']=depot
    logger.info('Asking user for rank and name')
    bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], text='Please enter rank & name:')
    return RNAME

def regHandler(update: Update, context: CallbackContext) -> int:
    bot = context.bot
    rankname = update.message.text
    depotname = depots[int(context.user_data['depot'])]
    userid = context.user_data['userid']
    if('users' not in context.bot_data):
        context.bot_data['users']={}
    context.bot_data['users'][userid]={
        'depot':depotname,
        'rankname':rankname,
        'reports':{}
    }
    logger.info('registration complete')
    bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], text=f'You have successfully registered as {rankname} from {depotname}.')    
    context.user_data.clear()
    context.chat_data.clear()
    return ConversationHandler.END

def cancelReg(update: Update, context: CallbackContext) -> int:
    '''Returns `ConversationHandler.END`, which tells the
    ConversationHandler that the conversation is over.
    '''
    bot = context.bot
    query = update.callback_query
    if(query is not None):
        query.answer()
        query.delete_message()
    bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['msgid'])
    try:    
        bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
    except:
        pass
    logger.info('User cancelled this action')
    bot.send_message(chat_id=update.effective_chat.id, text = 'Action cancelled')
    context.user_data.clear()
    context.chat_data.clear()
    return ConversationHandler.END

def deregister(update: Update, context: CallbackContext) -> None:
    bot = context.bot
    user = update.effective_user
    userid = user.id
    logger.info('Deregistering')
    if('users' not in context.bot_data):
        context.bot_data['users']={}
    if(userid not in context.bot_data['users']):
        bot.send_message(chat_id=update.effective_chat.id, text=f'User not registered!')
        return
    rname = context.bot_data['users'][userid]['rankname']
    context.bot_data['users'].pop(userid)
    bot.send_message(chat_id=update.effective_chat.id, text=f'User {rname} deregistered.')
    return
    
def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text('Help!')

def error_handler(update: object, context: CallbackContext) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f'An exception was raised while handling an update\n'
        f'<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}'
        '</pre>\n\n'
        f'<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n'
        f'<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n'
        f'<pre>{html.escape(tb_string)}</pre>'
    )

    # Finally, send the message
    context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML)


def main() -> None:
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    TOKEN = os.environ.get('TELE_BOT_TOKEN')
    updater = Updater(TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Setup conversation for adding cases
    add_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register)],
        states={
            DEPOT: [
                CallbackQueryHandler(plt)
            ],
            PLT: [
                MessageHandler(Filters.text & ~Filters.command, sect)
            ],
            SECT:   [
                MessageHandler(Filters.text & ~Filters.command, rname)
            ],
            RNAME:   [
                MessageHandler(Filters.text & ~Filters.command, ttype)
            ],
            TTYPE:   [
                CallbackQueryHandler(regHandler)
            ],
        },
        
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )

    # Add ConversationHandler to dispatcher that will be used for handling updates
    dispatcher.add_handler(add_handler)
    
    # Conversation handler for tools accounting
    acc_handler = ConversationHandler(
        entry_points=[CommandHandler('account', account)],
        states={
            DRAWER:   [
                CallbackQueryHandler(accountInlineHandler)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(acc_handler)

    # normal commands
    dispatcher.add_handler(CommandHandler('dereg', deregister))
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('help', help))

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':
    main()


