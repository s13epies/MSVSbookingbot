#!/usr/bin/env python
# pylint: disable=C0116,W0613
# This program is dedicated to the public domain under the CC0 license.

'''
Send /start to initiate the conversation.
Press Ctrl-C on the command line to stop the bot.
'''
import logging
import dateparser
from datetime import datetime, timedelta, timezone, tzinfo, time
import html
import json
import traceback
from requests import request
from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update, ParseMode, ForceReply
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    CallbackContext,
    MessageHandler,
    Filters,
)
from firebasepersistence import FirebasePersistence
from postgrespersistence import PostgresPersistence
import re
import os
import pytz
import base64
from calendar_generator import createImageAll, createImageDay, createImageWeek, get_calendar_service, get_event_list
# stuff for google calendar api
from os import path
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build

# PERMISSIONS FOR API ACCESS
SCOPES = ['https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/calendar']

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)


logger = logging.getLogger(__name__)

#static stuff
ROOMS = ['L1 Ops Hub', 'L1 Mercury Planning Room', 'L2 Venus Planning Room', 'L3 Terra Planning Room', 'Fortitude', 'Spark', 'Steadfast', 'Gearbox', 'Forward Laager','TRACKED VEHICLE MOVEMENT']
TRACK = 'TRACKED VEHICLE MOVEMENT' # for tracked booking
UNIT = ['SBW','AMB','40','41','42','48','ICT/TI','OTHERS'] # Unit
ROOM_VALIDATOR = [1,1,1,1,1,1,1,0,0,1]
RVNAME = ['S3/S4 1AMB', 'Camp Ops Manager, SBW']
AUTHTYPE, AUTH, RNAME, UNIT1, UNAME = range(5)   # for registration conversation
NRIC, PHONE = range(2)  # registration authentication type
ROOM, DATE, TIME, TIME2 = range(4) # for booking conversation
APPLIST = 1
SELECT_BOOKING, APPROVE_BOOKING = range(2)
PROMOTE = 1
t_offset = timedelta(hours=8)  # for date offset from server time
tz = timezone(timedelta(hours=8))
tz1 = pytz.timezone('Asia/Singapore')
# for error logging
PORT = int(os.environ.get('PORT', 5000))
regexstring = '^(ME[1-8][AT]?|REC|PTE|LCP|CPL|CFC|SCT|OCT|([1-3]|[MS])SG|([1-3]|[MSC])WO|2LT|LTA|CPT|MAJ|LTC|SLTC|COL|BG|MG|LG|GEN) [a-zA-Z][a-zA-Z ]+$'
rankname_validator = re.compile(regexstring)

# GOOGLE CALENDAR API UTILITY FUNCTIONS
# THIS ALLOWS US TO INTERACT WITH ALL GOOGLE APIS, IN THIS CASE CALENDAR

# CREATE CALENDAR
'''def create_calendar(template: dict):
    try:
        response = service.calendars().insert(body=template).execute()
        return response
    except Exception as e:
        return e.__class__
'''

# ---TELEGRAM COMMAND HANDLERS---

def register(update: Update, context: CallbackContext) -> int:   # Registration start point
    bot = context.bot
    user = update.effective_user
    context.user_data.clear()
    if('users' in context.bot_data):
        if(str(user.id) in context.bot_data['users'].keys()): # duplicate user
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
    context.user_data['msgid'] = update.message.reply_text(text='Please enter your name:').message_id
    return RNAME

#EDITED
def unit(update: Update, context: CallbackContext) -> int:
    rankname = update.message.text
    context.user_data['rankname']=rankname
    logger.info('Asking user for unit')
    keyboard = [
        [InlineKeyboardButton(f'{units}', callback_data=i)] for i, units in enumerate(UNIT)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msgid = update.message.reply_text(text=f'Please select your unit', reply_markup=reply_markup).message_id
    context.user_data['msgid'] = msgid
    return UNIT1

def regHandler(update: Update, context: CallbackContext) -> int:
    bot = context.bot
    if(update.callback_query is not None):
        query = update.callback_query
        unit = UNIT[int(query.data)]
        query.answer()
    else:
        unit = update.message.text
    
    if unit == UNIT[-1]:
        logger.info('registration complete')
        bot.send_message(chat_id=update.effective_chat.id, text=f'Please enter your unit name.')
        return UNIT1
    logger.info('At reg handler')
    userid = str(update.effective_user.id)
    rankname = context.user_data['rankname']
    nric = context.user_data['nric']
    phone = context.user_data['phone']
    auth_key = (str(nric),str(phone))
    if(auth_key in context.bot_data['approved']):
        context.bot_data['users'][userid]={
            'rankname':rankname,
            'unit':unit,
            'admin':False
        }
        logger.info('registration complete')
        bot.send_message(chat_id=update.effective_chat.id, text=f'You have successfully registered as {rankname} from {unit}.')    
    else:
        logger.info('registration pending approval')
        bot.send_message(chat_id=update.effective_chat.id, text=f'You are now pending registration as {rankname} from {unit}. Please ask an admin to approve you.') 
        context.bot_data['requests'][userid]={
                    'auth_key':auth_key,
                    'rankname':rankname,
                    'unit':unit
                }
        for user in context.bot_data['users'].keys():
            if(context.bot_data['users'][user]['admin']):
                bot.send_message(chat_id=int(user), text=f'{rankname}, {unit} has requested approval with NRIC:{auth_key[0]} & phone:{auth_key[1]}. Approve users with /approve.')   
    context.user_data.clear()
    return ConversationHandler.END
#END OF EDIT

def approve(update: Update, context: CallbackContext) -> int:
    userid = str(update.effective_user.id)
    if('users' in context.bot_data):
        if(userid not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /start to begin registration')
            return ConversationHandler.END
    bot = context.bot
    if(context.bot_data['users'][userid] is not None):
        if not context.bot_data['users'][userid]['admin']:
            bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'You are not an admin! Please contact an admin.')
            return ConversationHandler.END
    args = context.args
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
            un = d['unit']
            auth_key = d['auth_key']
            keyboard.append([InlineKeyboardButton(f'{rn} {un} ({auth_key[0]}:{auth_key[1]})', callback_data=str(uid))])
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
    query.answer()
    bot = context.bot
    if(auth_user=='cancel'):
        bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Action cancelled.')
        return ConversationHandler.END
    
    auth_user = str(auth_user)
    auth_dict = context.bot_data['requests'].pop(auth_user)
    auth_rankname = auth_dict['rankname']
    auth_unit = auth_dict['unit']
    context.bot_data['approved'].append(auth_dict['auth_key'])
    context.bot_data['users'][auth_user]={
            'rankname':auth_rankname,
            'unit':auth_unit,
            'admin':False
        }
    bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Approved user {auth_rankname} {auth_unit}')
    bot.send_message(
            chat_id=int(auth_user),
            text=f'You have been approved!')
    return ConversationHandler.END


# TODO APPROVE BOOKING BY ADMIN SYSTEM

def insertEvent(booking, booking_facility):
    service = get_calendar_service()
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    calendarId = cal_ids[booking_facility]
    
    e = service.events().insert(calendarId=calendarId, body=booking).execute()
    return e

def approveBooking(update: Update, context: CallbackContext) -> int:
    userid = str(update.effective_user.id)
    if('users' in context.bot_data):
        if(userid not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /start to begin registration')
            return ConversationHandler.END
    bot = context.bot
    if(context.bot_data['users'][userid] is not None):
        if not context.bot_data['users'][userid]['admin']:
            bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'You are not an admin! Please contact an admin.')
            return ConversationHandler.END
    keyboard = []
    if('booking_requests' not in context.bot_data.keys()):
        context.bot_data['booking_requests']=[]
    for i,request in enumerate(context.bot_data['booking_requests']):
        rn = request['rankname']
        un = request['unit']
        start = request['start']
        end = request['end']
        facility = request['facility']
        sdt = datetime.fromisoformat(start)
        edt = datetime.fromisoformat(end)
        timestring = sdt.strftime('%d/%m %H%M')+'-'+edt.strftime('%H%M')
        keyboard.append([InlineKeyboardButton(f'{ROOMS[facility]} {timestring} {rn} {un}', callback_data=str(i))])
    keyboard.append([InlineKeyboardButton(f'Cancel', callback_data=str('cancel'))])
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = bot.send_message(
        chat_id=update.effective_chat.id,
        text=f'Select a booking from the following:',
        reply_markup=reply_markup)
    context.user_data['msgid'] = msg.message_id
    return SELECT_BOOKING

def approveBookingConfirm(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    req = query.data
    query.answer()
    bot = context.bot
    if(req=='cancel'):
        bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Action cancelled.')
        return ConversationHandler.END
    keyboard = []
    keyboard.append([InlineKeyboardButton(f'Approve', callback_data=json.dumps([req,True]))])
    keyboard.append([InlineKeyboardButton(f'Deny', callback_data=json.dumps([req,False]))])
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id = context.user_data['msgid'],
        text=f'Approve booking?',
        reply_markup=reply_markup)
    return APPROVE_BOOKING


def approveBookingHandler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    req = json.loads(query.data)
    query.answer()
    bot = context.bot
    
    request = context.bot_data['booking_requests'][int(req[0])]
    rn = request['rankname']
    user = request['user']
    un = request['unit']
    start = request['start']
    end = request['end']
    facility = request['facility']
    sdt = datetime.fromisoformat(start)
    edt = datetime.fromisoformat(end)
    dt = sdt.strftime('%d/%m %H%M')+'-'+edt.strftime('%H%M')
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    calendarId = cal_ids[facility]
    event_list = get_event_list([calendarId], sdt, edt)
    nameunit = rn + ' ' + un
    booking = {
        'summary': nameunit,
        'start': {
            'dateTime': start,
        },
        'end': {
            'dateTime': end,
        },
    }
    
    if event_list:  # duplicate event
        booked = event_list[0]
        if booked==booking:
            #duplicate event
            bot.send_message(
                chat_id=update.effective_chat.id,
                text=f'Booking for {ROOMS[facility]} at {dt} is already approved!')
        else:
            bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id = context.user_data['msgid'],
                text=f'Denied booking for {ROOMS[facility]} at {dt}')
            bot.send_message(
                chat_id=int(user),
                text=f'Your booking has been denied as the selected timeslot is no longer available. Please book another timeslot.')
        
        context.bot_data['booking_requests'].pop(int(req[0]))
        return ConversationHandler.END
    
    if not req[1]:
        bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id = context.user_data['msgid'],
            text=f'Denied booking for {ROOMS[facility]} at {dt}')
        bot.send_message(
            chat_id=int(user),
            text=f'Your booking has been denied')
        context.bot_data['booking_requests'].pop(int(req[0]))
        return ConversationHandler.END
    
    context.bot_data['booking_requests'].pop(int(req[0]))
    e=insertEvent(booking,facility)    
    logger.info('Event created: %s' % (e.get('htmlLink')))
    bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id = context.user_data['msgid'],
            text=f'Approved booking for {ROOMS[facility]} at {dt}')
    bot.send_message(
            chat_id=int(user),
            text=f'Your booking has been approved!')
    context.user_data.clear()
    return ConversationHandler.END

def promote(update: Update, context: CallbackContext) -> int:
    bot = context.bot
    userid = str(update.effective_user.id)
    if('users' in context.bot_data):
        if(userid not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /start to begin registration')
            return ConversationHandler.END
    if(context.bot_data['users'][userid] is not None):
        if not context.bot_data['users'][userid]['admin']:
            bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'You are not an admin! Please contact an admin.')
            return ConversationHandler.END
    keyboard = []
    for uid, d in context.bot_data['users'].items():
        rn = d['rankname']
        un = d['unit']
        admin = d['admin']
        if not admin:
            keyboard.append([InlineKeyboardButton(f'{rn} {un}', callback_data=str(uid))])
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
    admin_user = str(admin_user)
    context.bot_data['users'][admin_user]['admin']=True
    admin_rn = context.bot_data['users'][admin_user]['rankname']
    admin_un = context.bot_data['users'][admin_user]['unit']
    query.answer()
    bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'Promoted user {admin_rn} {admin_un}')
    bot.send_message(
            chat_id=int(admin_user),
            text=f'You have been promoted!')
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
    userid = str(user.id)
    logger.info('Deregistering')
    if('users' not in context.bot_data):
        context.bot_data['users']={}
    if(userid not in context.bot_data['users']):
        bot.send_message(chat_id=update.effective_chat.id, text=f'User not registered!')
        return
    rname = context.bot_data['users'][userid]['rankname']
    unit = context.bot_data['users'][userid]['unit']
    context.bot_data['users'].pop(userid)
    bot.send_message(chat_id=update.effective_chat.id, text=f'User {rname} from {unit} deregistered.')
    return
    
def setup(update: Update, context: CallbackContext) -> None:
    '''if(update.effective_user.id!=DEVELOPER_CHAT_ID):
        update.message.reply_text('user not authorized')
        return'''
    if 'approved' not in context.bot_data:
        context.bot_data['approved']=[]
    DA = json.loads(os.environ.get('DEVELOPER_AUTH'))
    if DA not in context.bot_data['approved']:
        context.bot_data['approved'].append(DA)
    if 'users' not in context.bot_data:
        context.bot_data['users']={}
    if 'requests' not in context.bot_data:
        context.bot_data['requests']={}
    if('daily_job' not in context.bot_data):
        context.bot_data['daily_job'] =''
    if(context.job_queue.get_jobs_by_name(context.bot_data['daily_job']) is not None):
        for j in context.job_queue.get_jobs_by_name(context.bot_data['daily_job']):
            j.schedule_removal()
    # logger.info('Creating daily reminder')
    # job = context.job_queue.run_daily(reminder, days=(0, 1, 2, 3, 4), context=context,time = time(hour = 17, minute = 30, second = 00, tzinfo=tz1))
    # logger.info(f'next job execution at {job.next_t.isoformat()}')
    # context.bot_data['daily_job'] = job.name
    update.message.reply_text('Bot initialization complete!')
    
def reset(update: Update, context: CallbackContext) -> None:
    logger.info('reset bot')
    context.chat_data.clear()
    context.bot_data.clear()
    context.user_data.clear()
    bot = context.bot
    bot.send_message(chat_id=update.message.chat_id, text='Bot reset. Please use /setup to resume')
    
def softreset(update: Update, context: CallbackContext) -> None:
    logger.info('soft reset bot')
    context.chat_data.clear()
    context.user_data.clear()
    bot = context.bot
    bot.send_message(chat_id=update.message.chat_id, text='Soft reset performed.')
    
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
    DEVELOPER_CHAT_ID = int(os.environ.get('DEVELOPER_CHAT_ID'))
    if(update.effective_user.id!=DEVELOPER_CHAT_ID):
        update.message.reply_text('user not authorized')
        return
    context.bot_data['users'][str(DEVELOPER_CHAT_ID)]['admin']=True
      
def book(update: Update, context: CallbackContext) -> int:   # Registration start point
    user = update.effective_user
    if('users' in context.bot_data):
        if(str(user.id) not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /start to begin registration')
            return ConversationHandler.END
    context.user_data.clear()
    logger.info('Asking user for facility')
    keyboard = [
        [InlineKeyboardButton(f'{room}', callback_data=i)] for i, room in enumerate(ROOMS[:-1])
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msgid = update.message.reply_text(text=f'Please select the facility you would like to book', reply_markup=reply_markup).message_id
    context.user_data['msgid'] = msgid
    return ROOM

#EDITED
def booktrack(update: Update, context: CallbackContext) -> int:  # Tracked Registration start point
    user = update.effective_user
    if('users' in context.bot_data):
        if(str(user.id) not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /start to begin registration')
            return ConversationHandler.END
    context.user_data.clear()
    logger.info('Booking tracked vehicle movement')
    context.user_data['facility'] = 9
    bot = context.bot
    bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f'Please enter the date of booking for {TRACK}'
    )
    return DATE
#END OF EDIT

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

def time1(update: Update, context: CallbackContext) -> int:
    booking_date = update.message.text 
    bd = dateparser.parse(booking_date, settings={'DATE_ORDER': 'DMY'})
    logger.info(f'BD0={bd}')
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
    bd = datetime.combine(bd.date(), datetime.min.time(), tzinfo=tz)
    logger.info(f'BD={bd}')
    context.user_data['booking_date']=bd.isoformat()
    logger.info(f'booking for {booking_date}')
    
    booklist = f'Bookings for {booking_date}:\n'
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    booking_facility = int(context.user_data['facility'])
    calendarId = cal_ids[booking_facility]
    
    daystart_dt = bd
    dayend_dt = (bd+timedelta(days=1))
    event_list = get_event_list([calendarId], daystart_dt, dayend_dt)
    if not event_list:
        booklist+='None\n'
    for e in event_list:
        start_t = dateparser.parse(e['start']['dateTime']).astimezone(tz).strftime('%H%M')
        end_t = dateparser.parse(e['end']['dateTime']).astimezone(tz).strftime('%H%M')
        name = e['summary']
        booklist+=f'{name} [{start_t}-{end_t}]\n'
    context.user_data['msgid']=bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f'{booklist}Please enter your booking start time in 24 hour HHHH format.'
    ).message_id
    return TIME

def endtime(update: Update, context: CallbackContext) -> int:
    start_time = update.message.text
    bot = context.bot
    if(re.match('^([01]?[0-9]|2[0-3])[0-5][0-9]$',start_time) is None):   # input validation for input time format
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'Incorrect format. Please enter your booking start time in 24 hour HHHH format.'
            )
        except:
            pass
        return TIME
    else:
        context.user_data['start_time']=start_time
        context.user_data['msgid']=bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f'Please enter your booking end time in 24 hour HHHH format.'
        ).message_id
        return TIME2

def bookHandler(update: Update, context: CallbackContext) -> int:
    end_time = update.message.text
    bot = context.bot
    userid = str(update.effective_user.id)
    rankname = context.bot_data['users'][userid]['rankname']
    unit = context.bot_data['users'][userid]['unit']
    if(re.match('^([01]?[0-9]|2[0-3])[0-5][0-9]$',end_time) is None):   # input validation for input time format
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'Incorrect format. Please enter your booking end time in 24 hour HHHH format.'
            )
        except:
            pass
        return TIME2
    start_time = context.user_data['start_time']
    if(start_time>end_time):   # input validation for input time
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'End time must be later than start time. Please try again.'
            )
        except:
            pass
        return TIME2
    booking_time = start_time+'-'+end_time
    logger.info(f'booking at {booking_time}')
    booking_date = datetime.fromisoformat(context.user_data['booking_date']).astimezone(tz)
    bd_str = booking_date.strftime('%d/%m/%Y')
    booking_facility = int(context.user_data['facility'])
    bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
        text=f'Processing booking for {bd_str} {booking_time}... please wait'
    )
    start_dt = booking_date+timedelta(hours=float(start_time[:2]), minutes=float(start_time[-2:]))
    end_dt = booking_date+timedelta(hours=float(end_time[:2]), minutes=float(end_time[-2:]))
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    calendarId = cal_ids[booking_facility]
    event_list = get_event_list([calendarId], start_dt, end_dt)
    if event_list:
        booked = event_list[0]['summary']
        bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
            text=f'Cannot book {ROOMS[booking_facility]} on {bd_str} {booking_time}. Booking already made by {booked}. Use /cancel to cancel or enter your booking start and end time in 24 hour HHHH-HHHH format.'
        )
        return TIME
    
    if('booking_requests' not in context.bot_data.keys()):
        context.bot_data['booking_requests']=[]
    context.bot_data['booking_requests'].append({
        'rankname':rankname,
        'unit':unit,
        'user':userid,
        'start':start_dt.isoformat(),
        'end':end_dt.isoformat(),
        'facility':booking_facility
    })
    for user in context.bot_data['users'].keys():
        if(context.bot_data['users'][user]['admin']):
            bot.send_message(chat_id=int(user), text=f'{rankname}, {unit} has requested to book {ROOMS[booking_facility]} on {bd_str} at {booking_time}. Approve bookings with /approve_booking')   
    approval = RVNAME[ROOM_VALIDATOR[booking_facility]]
    # logger.info('Event created: %s' % (event.get('htmlLink')))
    bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f'Booking request made for {ROOMS[booking_facility]} on {bd_str} {booking_time}, pending approval from {approval}'
    )
    context.user_data.clear()
    return ConversationHandler.END

#EDITED
def bookTrackHandler(update: Update, context: CallbackContext) -> int:
    # service = get_calendar_service()
    end_time = update.message.text
    bot = context.bot
    userid = str(update.effective_user.id)
    rankname = context.bot_data['users'][userid]['rankname']
    unit = context.bot_data['users'][userid]['unit']
    # nameunit = rankname + ' ' + unit
    if(re.match('^([01]?[0-9]|2[0-3])[0-5][0-9]$',end_time) is None):   # input validation for input time format
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'Incorrect format. Please enter your booking end time in 24 hour HHHH format.'
            )
        except:
            pass
        return TIME2
    start_time = context.user_data['start_time']
    if(start_time>end_time):   # input validation for input time
        try:
            bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
                text=f'End time must be later than start time. Please try again.'
            )
        except:
            pass
        return TIME2
    booking_time = start_time+'-'+end_time
    logger.info(f'booking at {booking_time}')
    booking_date = datetime.fromisoformat(context.user_data['booking_date']).astimezone(tz)
    bd_str = booking_date.strftime('%d/%m/%Y')
    booking_facility = 9
    bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
        text=f'Processing booking for {bd_str} {booking_time}... please wait'
    )
    start_dt = booking_date+timedelta(hours=float(start_time[:2]), minutes=float(start_time[-2:]))
    logger.info(booking_date.isoformat())
    logger.info(start_dt.isoformat())
    end_dt = booking_date+timedelta(hours=float(end_time[:2]), minutes=float(end_time[-2:]))
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    
    calendarId = cal_ids[booking_facility]
    event_list = get_event_list([calendarId], start_dt, end_dt)
    if event_list:
        booked = event_list[0]['summary']
        bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=context.user_data['msgid'], 
            text=f'Cannot book {ROOMS[booking_facility]} on {bd_str} {booking_time}. Booking already made by {booked}. Use /cancel to cancel or enter your booking start and end time in 24 hour HHHH-HHHH format.'
        )
        return TIME
    if('booking_requests' not in context.bot_data.keys()):
        context.bot_data['booking_requests']=[]
    context.bot_data['booking_requests'].append({
        'rankname':rankname,
        'unit':unit,
        'user':userid,
        'start':start_dt.isoformat(),
        'end':end_dt.isoformat(),
        'facility':booking_facility
    })
    for user in context.bot_data['users'].keys():
        if(context.bot_data['users'][user]['admin']):
            bot.send_message(chat_id=int(user), text=f'{rankname}, {unit} has requested to book {ROOMS[booking_facility]} on {bd_str} at {booking_time}. Approve bookings with /approve_booking')   
    approval = RVNAME[ROOM_VALIDATOR[booking_facility]]
    # event = service.events().insert(calendarId=calendarId, body=booking).execute()
    # logger.info('Event created: %s' % (event.get('htmlLink')))
    bot.send_message(
        chat_id=update.effective_chat.id, 
        text=f'Booking request made for {TRACK} on {bd_str} {booking_time}, pending approval from {approval}'
    )
    context.user_data.clear()
    return ConversationHandler.END
#END OF EDIT
    
def delete(update: Update, context: CallbackContext) -> int:   # Registration start point
    user = update.effective_user
    context.user_data.clear()
    if('users' in context.bot_data):
        if(str(user.id) not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /start to begin registration')
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
    userid = str(update.effective_user.id)
    rankname = context.bot_data['users'][userid]['rankname']
    unit = context.bot_data['users'][userid]['unit']
    nameunit = rankname + ' ' + unit
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    booking_facility = int(context.user_data['facility'])
    calendarId = cal_ids[booking_facility]
    
    daystart_dt = bd.astimezone(tz)
    dayend_dt = (bd+timedelta(days=1)).astimezone(tz)
    event_list = get_event_list([calendarId], daystart_dt, dayend_dt)
    keyboard = []
    valid = False
    for e in event_list:
        start_t = dateparser.parse(e['start']['dateTime']).astimezone(tz).strftime('%H%M')
        end_t = dateparser.parse(e['end']['dateTime']).astimezone(tz).strftime('%H%M')
        name = e['summary']
        id = e['id']
        if(name==nameunit):
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

def viewDay(update: Update, context: CallbackContext) -> int:   # view start point
    user = update.effective_user
    if('users' in context.bot_data):
        if(str(user.id) not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /start to begin registration')
            return ConversationHandler.END
    logger.info('Asking user for date for viewing')
    msgid = update.message.reply_text(text=f'Please enter the date for viewing').message_id
    context.user_data['msgid'] = msgid
    return DATE

def viewDayHandler(update: Update, context: CallbackContext) -> int:
    booking_date = update.message.text 
    bd = dateparser.parse(booking_date, settings={'DATE_ORDER': 'DMY'})
    bd = datetime.combine(bd.date(), datetime.min.time(), tzinfo=tz)
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

def viewWeek(update: Update, context: CallbackContext) -> int:   # Registration start point
    user = update.effective_user
    context.user_data.clear()
    if('users' in context.bot_data):
        if(str(user.id) not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /start to begin registration')
            return ConversationHandler.END
    logger.info('Asking user for facility')
    keyboard = [
        [InlineKeyboardButton(f'{room}', callback_data=i)] for i, room in enumerate(ROOMS)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msgid = update.message.reply_text(text=f'Please select the facility you would like to view bookings for', reply_markup=reply_markup).message_id
    context.user_data['msgid'] = msgid
    return ROOM

def viewWeekHandler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    room = int(query.data)
    query.answer()
    bot = context.bot
    img = createImageWeek(room)
    logger.info(f'generating image for {ROOMS[room]}')
    bot.send_photo(chat_id=update.effective_chat.id, photo=img)
    return ConversationHandler.END
    
def view(update: Update, context: CallbackContext) -> int:
    bot = context.bot
    user = update.effective_user
    if('users' in context.bot_data):
        if(str(user.id) not in context.bot_data['users']): # user not registered
            update.message.reply_text(text='User not registered! Use /start to begin registration')
            return
    args = context.args
    now = None
    if(args is not None):
        argstr = ' '.join(args)
        now = dateparser.parse(argstr, settings={'DATE_ORDER': 'DMY'})
    img = createImageAll(now)
    logger.info(f'generating overview image')
    bot.send_photo(chat_id=update.effective_chat.id, photo=img)

def reminder(context: CallbackContext) -> int:
    bot = context.bot
    if('users' in context.bot_data):
        for user in context.bot_data['users']: 
            bot.send_message(int(user), f'This is a reminder to book msvs facilities. Use /book to begin.')
    return

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text(f'Use /start to begin registration and /dereg to deregister. \n'
                              f'Use /book to book rooms and /delete to delete a booking.\n' 
                              f'Use /view to see room bookings\n' 
                              f'Use /view_week to see availability of a room for this week\n' 
                              f'Use /view_day to see availability of all rooms for a particular day\n' 
                              f'Admins may use /approve to approve new user registrations or /promote to promote a user to admin.\n'
                              f'use /approve [NRIC] [Phone] to pre-approve users\n'
                              f'Use /cancel to cancel actions.')

def error_handler(update: object, context: CallbackContext) -> None:
    DEVELOPER_CHAT_ID = int(os.environ.get('DEVELOPER_CHAT_ID'))
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
        f'<pre>context.bot_data = {html.escape(str(context.bot_data))}</pre>\n\n'
        f'<pre>{html.escape(tb_string)}</pre>'
    )
    context.user_data.clear()
    # Finally, send the message
    context.bot.send_message(chat_id=int(DEVELOPER_CHAT_ID), text=message, parse_mode=ParseMode.HTML)
    context.bot.send_message(chat_id=update.effective_chat.id, text='An error has occurred. Please use /cancel to cancel this action.')

def init_testing_deploy():
    keys_64 = os.environ['keys']
    keys = base64.b64decode(keys_64).decode()
    data = json.loads(keys)
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
    '''
    DATABASE_URL = os.environ['DATABASE_URL']
    if('postgresql' not in DATABASE_URL):
        DATABASE_URL = DATABASE_URL.replace('postgres','postgresql',1)
        
    pers = PostgresPersistence(url=DATABASE_URL)'''
    pers = FirebasePersistence(database_url='https://console.firebase.google.com/u/0/project/msvs-bot/database/msvs-bot-default-rtdb/data/~2F', credentials=json.load('msvs-bot-firebase-adminsdk-4s2k3-5fe321f7b7.json'))
    updater = Updater(TOKEN, persistence=pers)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    # Setup conversation for registration
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler('start', register)],
        states={
            AUTHTYPE: [
                MessageHandler(Filters.text & ~Filters.command, auth)
            ],
            AUTH: [
                MessageHandler(Filters.text & ~Filters.command, rankname)
            ],
            RNAME:   [
                MessageHandler(Filters.text & ~Filters.command, unit)
            ],
            UNIT1: [
                CallbackQueryHandler(regHandler),
                MessageHandler(Filters.text & ~Filters.command, regHandler)
            ]
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
    
    # Setup conversation for user promotion
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
    book_handler = ConversationHandler(
        entry_points=[CommandHandler('book', book)],
        states={
            ROOM: [
                CallbackQueryHandler(date)
            ],
            DATE: [
                MessageHandler(Filters.text & ~Filters.command, time1)
            ],
            TIME: [
                MessageHandler(Filters.text & ~Filters.command, endtime)
            ],
            TIME2: [
                MessageHandler(Filters.text & ~Filters.command, bookHandler)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(book_handler)
    
    # Setup conversation for booking under tracked vehicle movement
    booktracked_handler = ConversationHandler(
        entry_points=[CommandHandler('book_tracked', booktrack)],
        states={
            DATE: [
                MessageHandler(Filters.text & ~Filters.command, time1)
            ],
            TIME: [
                MessageHandler(Filters.text & ~Filters.command, endtime)
            ],
            TIME2: [
                MessageHandler(Filters.text & ~Filters.command, bookTrackHandler)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(booktracked_handler)


    # Setup conversation for approving bookings
    booking_approve_handler = ConversationHandler(
        entry_points=[CommandHandler('approve_booking', approveBooking)],
        states={
            SELECT_BOOKING: [
                CallbackQueryHandler(approveBookingConfirm)
            ],
            APPROVE_BOOKING: [
                CallbackQueryHandler(approveBookingHandler)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(booking_approve_handler)
    
    # Setup conversation for booking deletion
    del_handler = ConversationHandler(
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
    dispatcher.add_handler(del_handler)
    
    # Setup conversation for viewing image for a set day
    view_day_handler = ConversationHandler(
        entry_points=[CommandHandler('view_day', viewDay)],
        states={
            DATE: [
                MessageHandler(Filters.text & ~Filters.command, viewDayHandler)
            ],
        },
        
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(view_day_handler)
    
    # Setup conversation for viewing image for a set facility
    view_week_handler = ConversationHandler(
        entry_points=[CommandHandler('view_week', viewWeek)],
        states={
            ROOM: [
                CallbackQueryHandler(viewWeekHandler)
            ],
        },
        
        fallbacks=[CommandHandler('cancel', cancelReg)],
    )
    dispatcher.add_handler(view_week_handler)
    
    # normal commands
    dispatcher.add_handler(CommandHandler('dereg', deregister))
    dispatcher.add_handler(CommandHandler('setup', setup))
    dispatcher.add_handler(CommandHandler('setupadmin', setupAdmin))
    dispatcher.add_handler(CommandHandler('help', help_command))
    dispatcher.add_handler(CommandHandler('view', view))
    dispatcher.add_handler(CommandHandler('reset', reset))
    dispatcher.add_handler(CommandHandler('softreset', softreset))
    dispatcher.add_handler(CommandHandler('cancel', cancelReg))
    # dispatcher.add_handler(CommandHandler('create_cals', create_cals))
    #Errors
    dispatcher.add_error_handler(error_handler)

    # Start the Bot
    
    updater.start_webhook(listen="0.0.0.0",
                          port=int(PORT),
                          url_path=TOKEN,
                          webhook_url=f"https://{N}.herokuapp.com/{TOKEN}")
                          
    # updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    
    updater.idle()

if __name__ == '__main__':
    main()
