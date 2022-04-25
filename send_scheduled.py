from asyncio.log import logger
from datetime import datetime, timedelta, timezone
import json
import time

import dateparser
from msvsbot import init_testing_deploy
import os
from postgrespersistence import PostgresPersistence
from telegram.ext import (
    Updater,
)
from calendar_generator import createImageAll, createImageDay, createImageWeek, get_calendar_service, get_event_list
def check_track_movement():
    tz = timezone(timedelta(hours=8))
    bd = datetime.today()
    bd = datetime.combine(bd.date(), datetime.min.time(), tzinfo=tz)
    logger.info(f'BD={bd}')
    booklist = f'Tracked Vehicle Movement for {bd.isoformat()}:\n'
    cal_ids = json.loads(os.environ.get("CALENDAR_ID"))
    calendarId = cal_ids[-1]
    daystart_dt = bd
    dayend_dt = (bd+timedelta(days=1))
    event_list = get_event_list([calendarId], daystart_dt, dayend_dt)
    if not event_list:
        return None
    for e in event_list:
        start_t = dateparser.parse(e['start']['dateTime']).astimezone(tz).strftime('%H%M')
        end_t = dateparser.parse(e['end']['dateTime']).astimezone(tz).strftime('%H%M')
        booklist+=f'[{start_t}-{end_t}]\n'
    return booklist

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
    tm = check_track_movement()
    logger.info(f'bot data:\n{json.dumps(bot_data)}')
    if not tm:
        updater.stop()
        logger.info(f'no track movements for today')
        return
    
    if('users' in bot_data):
        for user in bot_data['users']: 
            bot.send_message(int(user), f'Please be reminded that there will be tracked vehicle movement within MSVS today at these timings:\n{tm}')
        
        logger.info(f'track movements sent: {tm}')
    # updater.idle()
    time.sleep(5)
    updater.stop()
    return

if __name__ == '__main__':
    main()