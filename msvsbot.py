#!/usr/bin/env python
# pylint: disable=C0116,W0613
# This program is dedicated to the public domain under the CC0 license.

'''
Send /start to initiate the conversation.
Press Ctrl-C on the command line to stop the bot.
'''
import logging
import dateparser
from datetime import datetime, timedelta, timezone, tzinfo
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
import base64
from local_testing_init import define_env_vars
# stuff for google calendar api
from os import path
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build

# IF YOU MODIFY THE SCOPE DELETE THE TOKEN.TXT FILE
SCOPES = ['https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/calendar']

# THE TOKEN.TXT FILE STORES UPDATE AND USER ACCESS TOKENS

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)


logger = logging.getLogger(__name__)

#static stuff
ROOMS = ['L1 Ops Hub', 'L1 Mercury Planning Room', 'L2 Venus Planning Room', 'L3 Terra Planning Room', 'TRACKED VEHICLE MOVEMENT']
AUTHTYPE, AUTH, DEPOT, RNAME= range(4)   # for registration conversation
NRIC, PHONE = range(2)  # registration authentication type
ROOM, DATE, TIME = range(3) # for booking conversation
APPLIST = 1
PROMOTE = 1
t_offset = timedelta(hours=8)  # for date offset from server time
tz = timezone(timedelta(hours=8))
# for error logging
DEVELOPER_CHAT_ID = 291603849
PORT = int(os.environ.get('PORT', 5000))
regexstring = '^(ME[1-8][AT]?|REC|PTE|LCP|CPL|CFC|SCT|OCT|([1-3]|[MS])SG|([1-3]|[MSC])WO|2LT|LTA|CPT|MAJ|LTC|SLTC|COL|BG|MG|LG|GEN) [a-zA-Z][a-zA-Z ]+$'
rankname_validator = re.compile(regexstring)

# GOOGLE CALENDAR API UTILITY FUNCTIONS

def get_crendetials_google():
    # OPEN THE BROWSER TO AUTHORIZE
    flow = InstalledAppFlow.from_client_secrets_file("creds.json", SCOPES)
    creds = flow.run_local_server(port=0)

    # WE SAVE THE CREDENTIALS
    pickle.dump(creds, open("token.txt", "wb"))
    return creds

# THIS ALLOWS US TO INTERACT WITH ALL GOOGLE APIS, IN THIS CASE CALENDAR

def get_calendar_service():
    creds = None
    '''
    if path.exists("token.txt"):
        creds = pickle.load(open("token.txt", "rb"))
    # IF IT EXPIRED, WE REFRESH THE CREDENTIALS
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = get_crendetials_google()
    '''
    # key_file_location = 'msvskey.json'
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]), scopes=SCOPES)
    service = build("calendar", "v3", credentials=creds)

    return service


# METHODS

service = None

# CREATE CALENDAR
def create_calendar(template: dict):
    try:
        response = service.calendars().insert(body=template).execute()
        return response
    except Exception as e:
        return e.__class__

# CREATE EVENT
def create_event(template: dict, calendarId: str):
    try:
        response = service.events().insert(calendarId=calendarId, body=template).execute()
        return response
    except Exception as e:
        return e.__class__

# LIST EVENTS
def list_event(start: datetime, end: datetime, calendarId :str):
    try:
        response = service.events().list(calendarId=calendarId, ).execute()
        return response
    except Exception as e:
        return e.__class__


# DELETE EVENT BY ID
def delete_event(eventId: str, calendarId: str):
    try:
        response = service.events().delete(calendarId=calendarId, eventId=eventId).execute()
        return response
    except Exception as e:
        return e.__class__


# ---TELEGRAM COMMAND HANDLERS---

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
        if(user.id in context.bot_data['users'].keys()): # duplicate user
            update.message.reply_text(text='User already registered!')
            return ConversationHandler.END
    logger.info('Asking user for authentication type')
    keyboard = [
        [
            InlineKeyboardButton(f'NRIC', callback_data=NRIC),
            InlineKeyboardButton(f'Phone Number', callback_data=PHONE)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msgid = update.message.reply_text(text=f'Please select user authentication type', reply_markup=reply_markup).message_id
    context.user_data['msgid'] = msgid
    return AUTHTYPE

def auth(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    auth_type = int(query.data)  # select type of authentication
    context.user_data['auth_type']=auth_type
    logger.info(f'AUTH TYPE: {auth_type} {type(auth_type)}')
    logger.info('Asking user for authentication')
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

def rankname(update: Update, context: CallbackContext) -> int:
    auth_key = update.message.text
    auth_type = context.user_data['auth_type']
    auth_prompt = ''
    if(auth_type==NRIC):
        auth_val = '^[0-9]{3}[A-Z]$'
        auth_prompt = 'NRIC'
    elif(auth_type==PHONE):
        auth_val = '^[0-9]{4}$'
        auth_prompt = 'phone number'
    if(re.match(auth_val, auth_key) is None):
        bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], text=f'Invalid {auth_prompt}. Please try again.')
        return AUTH
    bot = context.bot
    context.user_data['auth_key']=auth_key
    logger.info('Asking user for rank and name')
    context.user_data['msgid'] = update.message.reply_text(text='Please enter rank & name:').message_id
    return RNAME

def regHandler(update: Update, context: CallbackContext) -> int:
    bot = context.bot
    rankname = update.message.text
    userid = context.user_data['userid']
    auth_type = context.user_data['auth_type']
    auth_key = context.user_data['auth_key']
    if(re.match(rankname_validator, rankname) is None):
        bot.edit_message_text(chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], text=f'Invalid rank and name. Please try again.')
        return RNAME
    if(auth_type==NRIC):
        autht = 'nric'
        auth_prompt = 'NRIC'
    elif(auth_type==PHONE):
        autht = 'phone'
        auth_prompt = 'phone'
    if(auth_key in context.bot_data['approved'][autht]):
        context.bot_data['users'][userid]={
            'rankname':rankname,
            'admin':False
        }
        logger.info('registration complete')
        bot.send_message(chat_id=update.effective_chat.id, text=f'You have successfully registered as {rankname}.')    
    else:
        logger.info('registration pending approval')
        bot.send_message(chat_id=update.effective_chat.id, text=f'You are now pending registration as {rankname}. Please ask an admin to approve you.') 
        context.bot_data['requests'][userid]={
                    'auth_type':auth_type,
                    'auth_key':auth_key,
                    'rankname':rankname
                }
        for user in context.chat_data['users'].keys():
            if(context.chat_data['users'][user]['admin']):
                bot.send_message(chat_id=user, text=f'{rankname} has requested approval with {auth_prompt}:{auth_key}. Approve users with /approve.')   
    context.user_data.clear()
    return ConversationHandler.END

def approve(update: Update, context: CallbackContext) -> int:
    userid = update.effective_user.id

    bot = context.bot
    if(context.bot_data['users'][userid] is not None):
        if not context.bot_data['users'][userid]['admin']:
            bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'You are not an admin! Please contact an admin.')
            return ConversationHandler.END
    args = context.args
    print(args)
    if(args is None):
        args = []
    if(len(args)==2):
        if(args[0].casefold()=='Phone'.casefold()):
            auth_type = PHONE
            auth_key = args[1]
        elif(args[0].casefold()=='NRIC'.casefold()):
            auth_type = NRIC
            auth_key = args[1]
        else:
            bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Invalid response! Please try again.')
            return ConversationHandler.END
    elif(len(args)==1):
        # assume NRIC registration
        auth_type = NRIC
        auth_key = args[0]
    elif(len(args)==0):
        keyboard = []
    
        for uid, d in context.bot_data['requests'].items():
            rn = d['rankname']
            auth_type = d['auth_type']
            auth_key = d['auth_key']
            if(auth_type==NRIC):
                autht = 'nric'
                auth_prompt = 'NRIC'
            elif(auth_type==PHONE):
                autht = 'phone'
                auth_prompt = 'phone'
            keyboard.append([InlineKeyboardButton(f'{rn} ({auth_prompt}:{auth_key})', callback_data=str(uid))])
        keyboard.append([InlineKeyboardButton(f'Cancel', callback_data=str('cancel'))])
        reply_markup = InlineKeyboardMarkup(keyboard)
        bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Select a user from the following:',
            reply_markup=reply_markup)
        return APPLIST
    else:
        bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Invalid response! Please try again.')
        return ConversationHandler.END
    if(auth_type==NRIC):
        autht = 'nric'
        auth_val = '^[0-9]{3}[A-Z]$'
        auth_prompt = 'NRIC'
    elif(auth_type==PHONE):
        autht = 'phone'
        auth_val = '^[0-9]{4}$'
        auth_prompt = 'phone'
    if(re.match(auth_val, auth_key) is None):
        bot.send_message(chat_id=update.effective_chat.id, text=f'Invalid {auth_prompt}. Please try again.')
    context.bot_data['approved'][autht].append(auth_key)
    bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Approved user {auth_prompt}:{auth_key}')
    return ConversationHandler.END

def approveHandler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    auth_user = int(query.data)
    if(auth_user=='cancel'):
        bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Action cancelled.')
        return ConversationHandler.END
    auth_dict = context.bot_data['requests'].get(auth_user)
    auth_rankname = auth_dict['rankname']
    query.answer()
    bot = context.bot
    bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Approved user {auth_rankname}')
    return ConversationHandler.END

def promote(update: Update, context: CallbackContext) -> int:
    bot = context.bot
    userid = update.effective_user.id
    if(context.bot_data['users'][userid] is not None):
        if not context.bot_data['users'][userid]['admin']:
            bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'You are not an admin! Please contact an admin.')
            return ConversationHandler.END
    keyboard = []
    for uid, d in context.bot_data['users'].items():
        rn = d['rankname']
        admin = d['admin']
        if not admin:
            keyboard.append([InlineKeyboardButton(f'{rn}', callback_data=str(uid))])
    keyboard.append([InlineKeyboardButton(f'Cancel', callback_data=str('cancel'))])
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.send_message(
        chat_id=update.effective_chat.id,
        text=f'Select a user from the following:',
        reply_markup=reply_markup)
    return PROMOTE

def promoteHandler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    admin_user = query.data
    bot = context.bot
    if(admin_user=='cancel'):
        bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Action cancelled.')
        return ConversationHandler.END
    admin_user = int(admin_user)
    context.bot_data['users'][admin_user]['admin']=True
    admin_rn = context.bot_data['users'][admin_user]['rankname']
    query.answer()
    bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Promoted user {admin_rn}')
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
    
def setup(update: Update, context: CallbackContext) -> None:
    if(update.effective_user.id!=DEVELOPER_CHAT_ID):
        update.message.reply_text('user not authorized')
        return
    context.bot_data['approved']={'nric':[],'phone':[]}
    context.bot_data['approved']['phone'].append('2481')
    context.bot_data['users']={}
    context.bot_data['requests']={}
    
###HELPER FUNCTION DONT RUN
'''def create_cals():
    calendar_details = [{'summary':x} for x in ROOMS]
    calendars = []
    for c in calendar_details:
        created = create_calendar(c)
        calendars.append(created)
    for i in calendars:
        rule = {
            'scope': {
                'type': 'user',
                'value': os.environ.get['ADMIN_EMAIL'],
            },
            'role': 'owner'
        }
        created_rule = service.acl().insert(calendarId=i['id'], body=rule).execute()
        print(created_rule['id'])'''
        

def setupAdmin(update: Update, context: CallbackContext) -> None:
    if(update.effective_user.id!=DEVELOPER_CHAT_ID):
        update.message.reply_text('user not authorized')
        return
    context.bot_data['users'][DEVELOPER_CHAT_ID]['admin']=True
    
    
def book(update: Update, context: CallbackContext) -> int:   # Registration start point
    bot = context.bot
    user = update.effective_user
    context.user_data.clear()
    context.user_data['userid'] = user.id   # Collect userid
    if('users' in context.bot_data):
        if(user.id not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /register to register')
            return ConversationHandler.END
    logger.info('Asking user for facility')
    keyboard = [
        [InlineKeyboardButton(f'{room}', callback_data=i)] for i, room in enumerate(ROOMS)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msgid = update.message.reply_text(text=f'Please select the facility you would like to book', reply_markup=reply_markup).message_id
    context.user_data['msgid'] = msgid
    return ROOM

def date(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    facility = int(query.data)  # select facility
    context.user_data['facility']=facility
    logger.info(f'user booking facility {ROOMS[facility]}')
    query.answer()
    bot = context.bot
    bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
        text=f'You are booking {ROOMS[facility]}. Please enter the date of your booking'
    )
    return DATE

def time(update: Update, context: CallbackContext) -> int:
    service = get_calendar_service()
    booking_date = update.message.text 
    bd = dateparser.parse(booking_date, settings={'DATE_ORDER': 'DMY'})
    bot = context.bot
    print(bd)
    print(datetime.today())
    if(bd is None or (bd.date()<(datetime.now().date()))):
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'Incorrect format. Please enter a valid booking date.'
            )
        except:
            pass
        return DATE
    context.user_data['booking_date']=bd.strftime('%d/%m/%Y')
    logger.info(f'booking for {booking_date}')
    
    booklist = f'Bookings for {booking_date}:\n'
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    booking_facility = int(context.user_data['facility'])
    calendarId = cal_ids[booking_facility]
    event_list = []
    daystart_dt = bd.astimezone(tz)
    dayend_dt = (bd+timedelta(days=1)).astimezone(tz)
    page_token = None
    while True:
        events = service.events().list(calendarId=calendarId, pageToken=page_token, timeMin=daystart_dt.isoformat(), timeMax = dayend_dt.isoformat()).execute()
        for event in events['items']:
            event_list.append({
                'summary':event['summary'],
                'start':event['start'],
                'end':event['end'],
                'id':event['id'],
            })
        page_token = events.get('nextPageToken')
        if not page_token:
            break
    if not event_list:
        booklist+='None\n'
    for e in event_list:
        start_t = datetime.fromisoformat(e['start']).strftime('%H%M')
        end_t = datetime.fromisoformat(e['end']).strftime('%H%M')
        name = e['summary']
        booklist+=f'{name} [{start_t}-{end_t}]\n'
    
    context.user_data['msgid']=bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f'{booklist}\nPlease enter your booking start and end time in 24 hour HHHH-HHHH format.'
    ).message_id
    return TIME

def bookHandler(update: Update, context: CallbackContext) -> int:
    service = get_calendar_service()
    booking_time = update.message.text
    bot = context.bot
    userid = context.user_data['userid']
    rankname = context.bot_data['users'][userid]['rankname']
    if(re.match('^([01]?[0-9]|2[0-3])[0-5][0-9]-([01]?[0-9]|2[0-3])[0-5][0-9]$',booking_time) is None):   # input validation for input time format
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'Incorrect format. Please enter your booking start and end time in 24 hour HHHH-HHHH format.'
            )
        except:
            pass
        return TIME
    start_time = booking_time[:4]
    end_time = booking_time[-4:]
    if(start_time>end_time):   # input validation for input time
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'Incorrect format. Please enter your booking start and end time in 24 hour HHHH-HHHH format.'
            )
        except:
            pass
        return TIME
    logger.info(f'booking for {booking_time}')
    booking_date = datetime.strptime(context.user_data['booking_date'],'%d/%m/%Y').astimezone(tz)
    booking_facility = int(context.user_data['facility'])
    bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
        text=f'Processing booking... please wait'
    )
    start_dt = booking_date+timedelta(hours=float(start_time[:2]), minutes=float(start_time[-2:]))
    end_dt = booking_date+timedelta(hours=float(end_time[:2]), minutes=float(end_time[-2:]))
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    event_list = []
    calendarId = cal_ids[booking_facility]
    page_token = None
    while True:
        events = service.events().list(calendarId=calendarId, pageToken=page_token, timeMin=start_dt.isoformat(), timeMax = end_dt.isoformat()).execute()
        for event in events['items']:
            event_list.append(event['summary'])
        page_token = events.get('nextPageToken')
        if not page_token:
            break
    if event_list:
        bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
            text=f'Cannot book {ROOMS[booking_facility]} on {bd_str} {booking_time}. Booking already made by {event_list[0]}. Use /cancel to cancel or enter your booking start and end time in 24 hour HHHH-HHHH format.'
        )
        return TIME
    booking = {
        'summary': rankname,
        'start': {
            'dateTime': start_dt.isoformat(),
        },
        'end': {
            'dateTime': end_dt.isoformat(),
        },
    }
    event = service.events().insert(calendarId=calendarId, body=booking).execute()
    logger.info('Event created: %s' % (event.get('htmlLink')))
    bd_str = booking_date.strftime('%d/%m/%Y')
    bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
        text=f'Booking made for {ROOMS[booking_facility]} on {bd_str} {booking_time}'
    )
    return ConversationHandler.END
    
def delete(update: Update, context: CallbackContext) -> int:   # Registration start point
    bot = context.bot
    user = update.effective_user
    context.user_data.clear()
    context.user_data['userid'] = user.id   # Collect userid
    if('users' in context.bot_data):
        if(user.id not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /register to register')
            return ConversationHandler.END
    logger.info('Asking user for facility')
    keyboard = [
        [InlineKeyboardButton(f'{room}', callback_data=i)] for i, room in enumerate(ROOMS)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msgid = update.message.reply_text(text=f'Please select the facility you are deleting booking for', reply_markup=reply_markup).message_id
    context.user_data['msgid'] = msgid
    return ROOM

def bookingDelete(update: Update, context: CallbackContext) -> int:
    booking_date = update.message.text 
    bd = dateparser.parse(booking_date, settings={'DATE_ORDER': 'DMY'})
    bot = context.bot
    print(bd)
    print(datetime.today())
    if(bd is None or (bd.date()<(datetime.now().date()))):
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'Incorrect format. Please enter a valid booking date.'
            )
        except:
            pass
        return DATE
    context.user_data['booking_date']=bd.strftime('%d/%m/%Y')
    logger.info(f'booking for {booking_date}')
    context.user_data['msgid']=bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f'Please enter your booking start and end time in 24 hour HHHH-HHHH format.'
    ).message_id
    return TIME

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
    context.user_data.clear()
    # Finally, send the message
    context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML)

def init_testing_local():
    with open('keys.json','r') as keyfile:
        data = json.load(keyfile)
        print(json.dumps(data))
        for k in data.keys():
            os.environ[k]=data[k]
    return

def init_testing_deploy():
    keys_64 = os.environ['keys']
    keys = base64.b64decode(keys_64).decode()
    data = json.loads(keys)
    print(data.keys())
    for k in data.keys():
        dk = data[k]
        if(type(dk) is not str):
            dk = json.dumps(dk)
        os.environ[k]=dk
    return

def main() -> None:
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    init_testing_deploy()
    TOKEN = os.environ.get('TELE_BOT_TOKEN')
    print(TOKEN)
    updater = Updater(TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    # Setup conversation for registration
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register)],
        states={
            AUTHTYPE: [
                CallbackQueryHandler(auth)
            ],
            AUTH: [
                MessageHandler(Filters.text & ~Filters.command, rankname)
            ],
            RNAME:   [
                MessageHandler(Filters.text & ~Filters.command, regHandler)
            ],
        },
        
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(reg_handler)
    
    # Setup conversation for registration approval
    approve_handler = ConversationHandler(
        entry_points=[CommandHandler('approve', approve)],
        states={
            APPLIST: [
                CallbackQueryHandler(approveHandler)
            ],
        },
        
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(approve_handler)
    
    # Setup conversation for registration approval
    promote_handler = ConversationHandler(
        entry_points=[CommandHandler('promote', promote)],
        states={
            APPLIST: [
                CallbackQueryHandler(promoteHandler)
            ],
        },
        
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(promote_handler)
    
    
    # Setup conversation for booking
    promote_handler = ConversationHandler(
        entry_points=[CommandHandler('book', book)],
        states={
            ROOM: [
                CallbackQueryHandler(date)
            ],
            DATE: [
                MessageHandler(Filters.text & ~Filters.command, time)
            ],
            TIME: [
                MessageHandler(Filters.text & ~Filters.command, bookHandler)
            ],
        },
        
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(promote_handler)
    # normal commands
    dispatcher.add_handler(CommandHandler('dereg', deregister))
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('setup', setup))
    
    dispatcher.add_handler(CommandHandler('setupadmin', setupAdmin))
    dispatcher.add_handler(CommandHandler('help', help))
    # dispatcher.add_handler(CommandHandler('create_cals', create_cals))
    #Errors
    dispatcher.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()
     

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':
    main()


