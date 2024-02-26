#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import asyncio 
import base64
import requests
import logging
import time
import configparser

from panoramisk import Manager, Message

config = configparser.ConfigParser()
config.read('config.ini')

# данные для доступа к AMI
HOST = config.get('asterisk', 'host')
PORT = config.get('asterisk', 'port')
USER = config.get('asterisk', 'username')
SECRET = config.get('asterisk', 'secret')

# Количество символов в номере
INTERNAL_COUNT = int(config.get('asterisk', 'internal_count'))

# Веб-адрес каталога записей
RECORDS_URL = config.get('asterisk', 'records_url')

# Подключение к битрикс
BITRIX_URL = config.get('bitrix', 'url')
CRM_CREATE = config.get('bitrix', 'crm_create')
SHOW_CARD = config.get('bitrix', 'show_card')

calls_data = {}

dial_status = {
    '16': 200,
    '17': 486,
    '19': 304,
    '20': 480,
    '21': 304,
    '31': 200,
    '34': 503,
    '38': 503,
    '127': 603
}

# Поиск пользователя Битрикс24
def find_user_id(internal_number):
    users_data = requests.post(f'{BITRIX_URL}user.get', {'ACTIVE': 'true'}).json()
    if 'result' in users_data:
        all_users = users_data['result']
        for user in all_users:
            if internal_number and user.get('UF_PHONE_INNER') == internal_number:
                return user['ID']
        return all_users[0]['ID']
    else:
        print('ОШИБКА!!!!! find_user_id', users_data)


# Регистрация звонка в Битрикс24
def register_call(bitrix_user_id, phone_number, call_type):
    register_param = {
        'USER_ID': bitrix_user_id,
        'PHONE_NUMBER': phone_number,
        'TYPE': call_type,
        'SHOW': SHOW_CARD,
        'CRM_CREATE': CRM_CREATE
    }

    call_data = requests.post(f'{BITRIX_URL}telephony.externalcall.register', 
                              json=register_param).json()
    if 'result' in call_data:
        return call_data['result']['CALL_ID']
    else:
        print('ОШИБКА!!!!! register_call', phone_number, call_data)


manager = Manager(
    host=os.getenv('AMI_HOST', HOST),
    port=os.getenv('AMI_PORT', PORT),
    username=os.getenv('AMI_USERNAME', USER),
    secret=os.getenv('AMI_SECRET', SECRET),
    ping_delay=10,  # Delay after start
    ping_interval=10,  # Periodically ping AMI (dead or alive)
    reconnect_timeout=0.1,  # Timeout reconnect if connection lost
)


def on_connect(mngr: Manager):
    logging.info(
        'Connected to %s:%s AMI socket successfully' %
        (mngr.config['host'], mngr.config['port'])
    )


def on_login(mngr: Manager):
    logging.info(
        'Connected user:%s to AMI %s:%s successfully' %
        (mngr.config['username'], mngr.config['host'], mngr.config['port'])
    )


def on_disconnect(mngr: Manager, exc: Exception):
    logging.info(
        'Disconnect user:%s from AMI %s:%s' %
        (mngr.config['username'], mngr.config['host'], mngr.config['port'])
    )
    logging.debug(str(exc))


async def on_startup(mngr: Manager):
    await asyncio.sleep(0.1)
    logging.info('Something action...')


async def on_shutdown(mngr: Manager):
    await asyncio.sleep(0.1)
    logging.info(
        'Shutdown AMI connection on %s:%s' % (mngr.config['host'], mngr.config['port'])
    )


@manager.register_event('*')  # Register all events
async def ami_callback(mngr: Manager, message: Message):
    call_id = message.Linkedid
    if message.Event == 'Newchannel' and message.ChannelState != '0':

        if message.Context in ['from-trunk', 'from-pstn']:
            calls_data[call_id] = {'start_time': time.time()}
            calls_data[call_id]['phone_number'] = message.CallerIDNum

        if message.Context in ['from-internal'] and len(message.Exten) > INTERNAL_COUNT:
            calls_data[call_id] = {'start_time': time.time()}
            bitrix_user_id = find_user_id(message.CallerIDNum)
            bitrix_call_id = register_call(bitrix_user_id, message.Exten, 1)
            calls_data[call_id]['bitrix_user_id'] = bitrix_user_id
            calls_data[call_id]['bitrix_call_id'] = bitrix_call_id
            calls_data[call_id]['phone_number'] = message.Exten
    
    elif call_id not in calls_data:
        return
    
    # Получение пути файла записи разговора
    elif message.Variable == 'MIXMONITOR_FILENAME':
        if 'file_patch' not in calls_data[call_id]:
            calls_data[call_id]['file_patch'] = message.Value.split("monitor/")[1]
            calls_data[call_id]['file_name'] = os.path.basename(message.Value)

    # Ответ на звонок
    elif message.Event == 'BridgeEnter':
        if message.Priority != '1':
            return
        # Исходящий
        if message.Context in ['from-trunk', 'from-pstn']:
            calls_data[call_id]['call_status'] = 200

        # Входящий
        elif message.Context in ['macro-dial-one', 'from-internal']:
            bitrix_user_id = find_user_id(message.CallerIDNum)
            bitrix_call_id = register_call(bitrix_user_id, calls_data[call_id]['phone_number'], 2)
            calls_data[call_id]['bitrix_user_id'] = bitrix_user_id
            calls_data[call_id]['bitrix_call_id'] = bitrix_call_id
            calls_data[call_id]['call_status'] = 200

    # Звонок завершён
    elif message.Event == 'Hangup' and message.Context not in ['from-internal', 'from-queue']:
        if 'call_status' not in calls_data[call_id]:
            calls_data[call_id]["call_status"] = dial_status.get(message.Cause, '603')

        if 'bitrix_user_id' not in calls_data[call_id]:
            if message.Context in ['macro-dial-one']:
                calls_data[call_id]['bitrix_user_id'] = find_user_id(message.CallerIDNum)
            else:
                calls_data[call_id]['bitrix_user_id'] = find_user_id(None)
                calls_data[call_id]["call_status"] = 304
            calls_data[call_id]["bitrix_call_id"] = register_call(calls_data[call_id]['bitrix_user_id'], 
                                                                  calls_data[call_id]['phone_number'], 
                                                                  2)
        # Закрытие звонка в битрикс
        finish_param = {
        'CALL_ID': calls_data[call_id]["bitrix_call_id"],
        'USER_ID': calls_data[call_id]["bitrix_user_id"],
        'DURATION': round(time.time() - calls_data[call_id]["start_time"]),
        'STATUS_CODE': calls_data[call_id]["call_status"]
        }

        requests.post(f'{BITRIX_URL}telephony.externalcall.finish', finish_param)

        if calls_data[call_id]["call_status"] == 200:
            file_url = f'{RECORDS_URL}{calls_data[call_id]["file_patch"]}'
            response = requests.get(file_url)
            if response.status_code == 200:
                encoded_file = base64.b64encode(response.content)

            file_data = {
                'CALL_ID': calls_data[call_id]["bitrix_call_id"],
                'FILENAME': calls_data[call_id]["file_name"],
                'FILE_CONTENT': encoded_file
            }

            response_attachRecord = requests.post(f'{BITRIX_URL}telephony.externalCall.attachRecord', file_data).json()
       
        del calls_data[call_id]
        print(calls_data)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    manager.on_connect = on_connect
    manager.on_login = on_login
    manager.on_disconnect = on_disconnect
    manager.connect(run_forever=True, on_startup=on_startup, on_shutdown=on_shutdown)