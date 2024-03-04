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
RECORDS_URL = config.get('asterisk', 'records_url')
INTERNAL_COUNT = int(config.get('asterisk', 'internal_count'))

# Подключение к битрикс
BITRIX_URL = config.get('bitrix', 'url')
CRM_CREATE = config.get('bitrix', 'crm_create')
SHOW_CARD = config.get('bitrix', 'show_card')
DEFAULT_USER_ID = config.get('bitrix', 'default_user_id')

def to_list(input_string):
    return [item.strip() for item in input_string.split(',')]

INBOUND_CONTEXTS = to_list(config.get('asterisk', 'inbound_contexts'))
INTERNAL_CONTEXTS = to_list(config.get('asterisk', 'internal_contexts'))
HANGUP_DELISTING = to_list(config.get('asterisk', 'hangup_delisting'))

calls_data = {}

dial_status = {
    '3': 503,
    '16': 200,
    '17': 486,
    '19': 304,
    '20': 480,
    '21': 304,
    '31': 200,
    '34': 404,
    '38': 503,
    '127': 603
}

# Поиск пользователя Битрикс24
def find_user_id(internal_number):
    if internal_number is None and DEFAULT_USER_ID:
        return DEFAULT_USER_ID
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


async def on_shutdown(mngr: Manager):
    await asyncio.sleep(0.1)
    logging.info(
        'Shutdown AMI connection on %s:%s' % (mngr.config['host'], mngr.config['port'])
    )


@manager.register_event('*')  # Register all events
async def ami_callback(mngr: Manager, message: Message):
    call_id = message.Linkedid
    if message.Event == 'Newchannel' and message.Exten != 's':

        if message.Context in INBOUND_CONTEXTS:
            calls_data[call_id] = {'start_time': time.time()}
            calls_data[call_id]['phone_number'] = message.CallerIDNum

        if message.Context in INTERNAL_CONTEXTS and len(message.Exten) > INTERNAL_COUNT:
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
        if message.Context in INBOUND_CONTEXTS:
            calls_data[call_id]['call_status'] = 200

        # Входящий
        elif message.Context in INTERNAL_CONTEXTS:
            bitrix_user_id = find_user_id(message.CallerIDNum)
            bitrix_call_id = register_call(bitrix_user_id, calls_data[call_id]['phone_number'], 2)
            calls_data[call_id]['bitrix_user_id'] = bitrix_user_id
            calls_data[call_id]['bitrix_call_id'] = bitrix_call_id
            calls_data[call_id]['call_status'] = 200

    
    elif message.Event == 'Hangup' and message.Context not in HANGUP_DELISTING:
        call_data = calls_data.get(call_id, {})
        # Установка статуса звонка, если он еще не установлен
        if 'call_status' not in call_data:
            call_data["call_status"] = dial_status.get(message.Cause, '603')

        # Добавление bitrix_user_id, если его нет
        if 'bitrix_user_id' not in call_data:
            user_id_context = 'macro-dial-one' if message.Context in ['macro-dial-one'] else None
            bitrix_user_id = find_user_id(message.CallerIDNum if user_id_context else None)
            call_data['bitrix_user_id'] = bitrix_user_id
            
            # Установка статуса звонка в 304, если контекст не 'macro-dial-one'
            if not user_id_context:
                call_data["call_status"] = 304
            
            # Регистрация звонка в Bitrix
            call_data["bitrix_call_id"] = register_call(bitrix_user_id, call_data.get('phone_number'), 2)

        # Закрытие звонка в битрикс
        finish_param = {
        'CALL_ID': call_data["bitrix_call_id"],
        'USER_ID': call_data["bitrix_user_id"],
        'DURATION': round(time.time() - call_data["start_time"]),
        'STATUS_CODE': call_data["call_status"]
        }

        requests.post(f'{BITRIX_URL}telephony.externalcall.finish', finish_param)

        # передача записи звонка
        if call_data["call_status"] == 200:
            file_url = f'{RECORDS_URL}{call_data["file_patch"]}'
            response = requests.get(file_url)
            if response.status_code == 200:
                encoded_file = base64.b64encode(response.content)

                file_data = {
                    'CALL_ID': call_data["bitrix_call_id"],
                    'FILENAME': call_data["file_name"],
                    'FILE_CONTENT': encoded_file
                }

                requests.post(f'{BITRIX_URL}telephony.externalCall.attachRecord', file_data).json()
       
        del calls_data[call_id]
        print(calls_data)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    manager.on_connect = on_connect
    manager.on_login = on_login
    manager.on_disconnect = on_disconnect
    manager.connect(run_forever=True, on_shutdown=on_shutdown)