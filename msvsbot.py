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
from postgrespersistence import PostgresPersistence
import re
import os
import base64
import matplotlib.pyplot as plt
from PIL import Image
import io
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

# CREATE CALENDAR
'''def create_calendar(template: dict):
    try:
        response = service.calendars().insert(body=template).execute()
        return response
    except Exception as e:
        return e.__class__
'''

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
    if('users' in context.bot_data):
        if(user.id in context.bot_data['users'].keys()): # duplicate user
            update.message.reply_text(text='User already registered!')
            return ConversationHandler.END
    logger.info('Asking user for NRIC')
    msgid = update.message.reply_text(text=f'Please enter the last 4 characters of your NRIC',).message_id
    context.user_data['msgid'] = msgid
    return AUTHTYPE

def auth(update: Update, context: CallbackContext) -> int:
    nric = update.message.text
    if(re.match('^[0-9]{3}[A-Z]$', nric) is None):
        try:
            update.message.reply_text(text='Invalid NRIC, please try again')
        except:
            update.effective_chat.send_message(text='Invalid NRIC, please try again')
        return AUTHTYPE
    context.user_data['nric']=nric
    logger.info(f'NRIC: {nric}')
    logger.info('Asking user for phone number')
    update.message.reply_text(
        text=f'Please enter the last 4 digits of your phone number'
    )
    return AUTH

def rankname(update: Update, context: CallbackContext) -> int:
    phone = update.message.text
    if(re.match('^[0-9]{4}$', phone) is None):
        try:
            update.message.reply_text(text='Invalid phone number last 4 digits, please try again')
        except:
            update.effective_chat.send_message(text='Invalid phone number last 4 digits, please try again')
        return AUTH
    context.user_data['phone']=phone
    logger.info('Asking user for rank and name')
    context.user_data['msgid'] = update.message.reply_text(text='Please enter rank & name:').message_id
    return RNAME

def regHandler(update: Update, context: CallbackContext) -> int:
    bot = context.bot
    rankname = update.message.text
    userid = update.effective_user.id
    nric = context.user_data['nric']
    phone = context.user_data['phone']
    auth_key = [str(nric),str(phone)]
    if(auth_key in context.bot_data['approved']):
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
                    'auth_key':auth_key,
                    'rankname':rankname
                }
        for user in context.bot_data['users'].keys():
            if(context.bot_data['users'][user]['admin']):
                bot.send_message(chat_id=user, text=f'{rankname} has requested approval with NRIC:{auth_key[0]} & phone{auth_key[1]}. Approve users with /approve.')   
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
        auth_key = [args[0], args[1]]
        if(re.match('^[0-9]{4}$',auth_key[1]) is not None and re.match('^[0-9]{3}[A-Z]$', auth_key[0]) is not None):
            context.bot_data['approved'].append(auth_key)
            bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f'Approved user {auth_key[0]}:{auth_key[1]}')
            return ConversationHandler.END
        else:
            bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Invalid response! Please try again.')
            return ConversationHandler.END
    elif(len(args)==0):
        keyboard = []
        for uid, d in context.bot_data['requests'].items():
            rn = d['rankname']
            auth_key = d['auth_key']
            keyboard.append([InlineKeyboardButton(f'{rn} ({auth_key[0]}:{auth_key[1]})', callback_data=str(uid))])
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
   
    

def approveHandler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    auth_user = query.data
    bot = context.bot
    if(auth_user=='cancel'):
        query.answer()
        bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Action cancelled.')
        return ConversationHandler.END
    
    auth_user = int(auth_user)
    auth_dict = context.bot_data['requests'].get(auth_user)
    auth_rankname = auth_dict['rankname']
    query.answer()
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
        query.answer()
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
    context.bot_data['approved']=[]
    context.bot_data['approved'].append(['414I','2481'])
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
        text=f'Please enter the date of booking for {ROOMS[facility]}'
    )
    return DATE

def time(update: Update, context: CallbackContext) -> int:
    service = get_calendar_service()
    booking_date = update.message.text 
    bd = dateparser.parse(booking_date, settings={'DATE_ORDER': 'DMY'})
    bot = context.bot
    if(bd is None or (bd.date()<(datetime.now().date()))):
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'Incorrect format. Please enter a valid booking date.'
            )
        except:
            bot.send_message(
                chat_id=update.effective_chat.id,  
                text=f'Incorrect format. Please enter a valid booking date.'
            )
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
        start_t = dateparser.parse(e['start']['dateTime']).astimezone(tz).strftime('%H%M')
        end_t = dateparser.parse(e['end']['dateTime']).astimezone(tz).strftime('%H%M')
        name = e['summary']
        booklist+=f'{name} [{start_t}-{end_t}]\n'
    
    context.user_data['msgid']=bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f'{booklist}Please enter your booking start and end time in 24 hour HHHH-HHHH format.'
    ).message_id
    return TIME

def bookHandler(update: Update, context: CallbackContext) -> int:
    service = get_calendar_service()
    booking_time = update.message.text
    bot = context.bot
    userid = update.effective_user.id
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
    bd_str = booking_date.strftime('%d/%m/%Y')
    booking_facility = int(context.user_data['facility'])
    bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
        text=f'Processing booking for {bd_str} {booking_time}... please wait'
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
    bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f'Booking made for {ROOMS[booking_facility]} on {bd_str} {booking_time}'
    )
    context.user_data.clear()
    return ConversationHandler.END
    
def delete(update: Update, context: CallbackContext) -> int:   # Registration start point
    bot = context.bot
    user = update.effective_user
    context.user_data.clear()
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
    service = get_calendar_service()
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
    logger.info(f'removing booking for {booking_date}')
    userid = update.effective_user.id
    rankname = context.bot_data['users'][userid]['rankname']
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
    keyboard = []
    valid = False
    for e in event_list:
        start_t = dateparser.parse(e['start']['dateTime']).astimezone(tz).strftime('%H%M')
        end_t = dateparser.parse(e['end']['dateTime']).astimezone(tz).strftime('%H%M')
        name = e['summary']
        id = e['id']
        if(name==rankname):
            valid = True
            keyboard.append([InlineKeyboardButton(f'[{start_t}-{end_t}]', callback_data=id)])
    if not valid:
        try:
            bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f'No valid bookings to be deleted, please enter another date or use /cancel to cancel',
            )
        except:
            pass
        return DATE
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data['msgid']=bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f'Please select the booking to be deleted.',
        reply_markup=reply_markup
    ).message_id
    return TIME

def deleteHandler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    booking_to_delete = query.data
    query.answer()
    service = get_calendar_service()
    bot = context.bot
    logger.info(f'removing booking for id {booking_to_delete}')
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    booking_facility = int(context.user_data['facility'])
    calendarId = cal_ids[booking_facility]
    service.events().delete(calendarId=calendarId, eventId=booking_to_delete).execute()
    bot.edit_message_text(
        chat_id=update.effective_chat.id, 
        message_id=context.user_data['msgid'], 
        text=f'Booking deleted.'
    ).message_id
    return ConversationHandler.END

def createImageDay(day:datetime):  
    rooms=ROOMS
    colors=['pink', 'lightgreen', 'lightblue', 'wheat', 'salmon']    
    fig=plt.figure(figsize=(10,5.89))
    booking_date = day.strftime('%d/%m/%Y')
    service = get_calendar_service()
    booklist = f'Bookings for {booking_date}:\n'
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    event_list = []
    daystart_dt = day.astimezone(tz)
    dayend_dt = (day+timedelta(days=1)).astimezone(tz)
    for i, calendarId in enumerate(cal_ids):
        page_token = None
        while True:
            events = service.events().list(calendarId=calendarId, pageToken=page_token, timeMin=daystart_dt.isoformat(), timeMax = dayend_dt.isoformat()).execute()
            for event in events['items']:
                event_list.append({
                    'summary':event['summary'],
                    'start':event['start'],
                    'end':event['end'],
                    'room':i+1,
                })
            page_token = events.get('nextPageToken')
            if not page_token:
                break
    
    for e in event_list:
        event=e['summary']
        # data=map(float, data[:-1])
        room=e['room']-0.48
        start_t = dateparser.parse(e['start']['dateTime']).astimezone(tz)
        end_t = dateparser.parse(e['end']['dateTime']).astimezone(tz)
        name = e['summary']
        booklist+=f'{name} [{start_t}-{end_t}]\n'
        start=start_t.hour+start_t.minute/60
        end=end_t.hour+end_t.minute/60
        # plot event
        plt.fill_between([room, room+0.96], [start, start], [end,end], color=colors[int(e['room']-1)], edgecolor='k', linewidth=0.5)
        # plot beginning time
        plt.text(room+0.02, start+0.05 ,'{0}:{1:0>2}'.format(int(start_t.hour),int(start_t.minute)), va='top', fontsize=7)
        # plot end time
        # plt.text(room+0.02, start+0.05 ,'{0}:{1:0>2}'.format(int(end_t.hour),int(end_t.minute)), va='bottom', fontsize=7)
        # plot event name
        plt.text(room+0.48, (start+end)*0.5, event, ha='center', va='center', fontsize=11)

    # Set Axis
    ax=fig.add_subplot(111)
    ax.yaxis.grid()
    ax.set_xlim(0.5,len(rooms)+0.5)
    ax.set_ylim(15.1, 8.9)
    ax.set_xticks(range(1,len(rooms)+1))
    ax.set_xticklabels(rooms)
    ax.set_ylabel('Time')

    # Set Second Axis
    ax2=ax.twiny().twinx()
    ax2.set_xlim(ax.get_xlim())
    ax2.set_ylim(ax.get_ylim())
    ax2.set_xticks(ax.get_xticks())
    ax2.set_xticklabels(rooms)
    ax2.set_ylabel('Time')

    plt.title(booking_date,y=1.07)
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    return buf

def viewDay(update: Update, context: CallbackContext) -> int:   # view start point
    bot = context.bot
    user = update.effective_user
    if('users' in context.bot_data):
        if(user.id not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /register to register')
            return ConversationHandler.END
    logger.info('Asking user for date for viewing')
    msgid = update.message.reply_text(text=f'Please enter the date for viewing').message_id
    context.user_data['msgid'] = msgid
    return DATE

def viewDayHandler(update: Update, context: CallbackContext) -> int:
    booking_date = update.message.text 
    bd = dateparser.parse(booking_date, settings={'DATE_ORDER': 'DMY'})
    bot = context.bot
    if(bd is None or (bd.date()<(datetime.now().date()))):
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'Incorrect format. Please enter a valid booking date.'
            )
        except:
            bot.send_message(
                chat_id=update.effective_chat.id,  
                text=f'Incorrect format. Please enter a valid booking date.'
            )
        return DATE
    img = createImageDay(bd)
    logger.info(f'generating image for {booking_date}')
    bot.send_photo(chat_id=update.effective_chat.id, photo=img)
    return ConversationHandler.END

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
    N = 'msvs-bot'
    DATABASE_URL = os.environ['DATABASE_URL']
    if('postgresql' not in DATABASE_URL):
        DATABASE_URL = DATABASE_URL.replace('postgres','postgresql',1)
        
    pers = PostgresPersistence(url=DATABASE_URL)
    updater = Updater(TOKEN, persistence=pers)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    # Setup conversation for registration
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register)],
        states={
            AUTHTYPE: [
                MessageHandler(Filters.text & ~Filters.command, auth)
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
    del_handler = ConversationHandler(
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
    dispatcher.add_handler(del_handler)
    
    # Setup conversation for booking deletion
    booking_handler = ConversationHandler(
        entry_points=[CommandHandler('delete', delete)],
        states={
            ROOM: [
                CallbackQueryHandler(date)
            ],
            
            DATE: [
                MessageHandler(Filters.text & ~Filters.command, bookingDelete)
            ],
            TIME: [
                CallbackQueryHandler(deleteHandler)
            ],
        },
        
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(booking_handler)
    
    # Setup conversation for viewing image
    view_day_handler = ConversationHandler(
        entry_points=[CommandHandler('viewDay', viewDay)],
        states={
            DATE: [
                MessageHandler(Filters.text & ~Filters.command, viewDayHandler)
            ],
        },
        
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(view_day_handler)
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
    
    updater.start_webhook(listen="0.0.0.0",
                          port=int(PORT),
                          url_path=TOKEN,
                          webhook_url=f"https://{N}.herokuapp.com/{TOKEN}")
     

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':
    main()


