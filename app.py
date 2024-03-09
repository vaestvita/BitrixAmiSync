import os
import asyncio 
import base64
import requests
import logging
import time
import configparser

from panoramisk import Manager, Message

import bitrix

config = configparser.ConfigParser()
config.read('config.ini')

# данные для доступа к AMI
HOST = config.get('asterisk', 'host')
PORT = config.get('asterisk', 'port')
USER = config.get('asterisk', 'username')
SECRET = config.get('asterisk', 'secret')
RECORDS_URL = config.get('asterisk', 'records_url')
INTERNAL_COUNT = int(config.get('asterisk', 'internal_count'))

def to_list(input_string):
    return [item.strip() for item in input_string.split(',')]

INBOUND_CONTEXTS = to_list(config.get('asterisk', 'inbound_contexts'))
HANGUP_DELISTING = to_list(config.get('asterisk', 'hangup_delisting'))

calls_data = {}

dial_status = {
    '3': 503,
    '17': 486,
    '19': 304,
    '20': 480,
    '21': 304,
    '31': 200,
    '34': 404,
    '38': 503,
    '127': 603
}


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
    if message.Event == 'Newchannel':

        # Входящий звонок
        if message.Context in INBOUND_CONTEXTS:
            if call_id in calls_data:
                return
            calls_data[call_id] = {'start_time': time.time()}
            calls_data[call_id]['phone_number'] = message.CallerIDNum

        # Регистрация звонка и карточка
        elif message.Context == 'from-internal':
            if message.Exten == 's':
                bitrix_user_id, deafault_user = bitrix.get_user_id(message.CallerIDNum)
                # Для первого в очереди или единственного вн номера
                if 'bitrix_call_id' not in calls_data[call_id]:
                    calls_data[call_id]['bitrix_user_id'] = bitrix_user_id
                    bitrix_call_id = bitrix.register_call(bitrix_user_id, calls_data[call_id]['phone_number'], 2)
                    calls_data[call_id]['bitrix_call_id'] = bitrix_call_id

                # Для последующих в очереди или группе показываем карточку
                else:
                    if not deafault_user:
                        bitrix.card_action(calls_data[call_id]['bitrix_call_id'], bitrix_user_id, 'show')

            # Исходящий звонок - регистрация
            elif len(message.Exten) > INTERNAL_COUNT:
                calls_data[call_id] = {'start_time': time.time()}
                bitrix_user_id, deafault_user = bitrix.get_user_id(message.CallerIDNum)
                calls_data[call_id]['bitrix_user_id'] = bitrix_user_id
                bitrix_call_id = bitrix.register_call(bitrix_user_id, message.Exten, 1)
                calls_data[call_id]['bitrix_call_id'] = bitrix_call_id
    
    
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
        if message.Context == 'macro-dial-one':
            bitrix_user_id, deafault_user = bitrix.get_user_id(message.CallerIDNum)
            calls_data[call_id]['bitrix_user_id'] = bitrix_user_id

        calls_data[call_id]['call_status'] = 200

    # Завершение звонка
    elif message.Event == 'Hangup':
        call_data = calls_data.get(call_id)
        if message.Context == 'from-internal':

            # Если перезагрузка звонка в очереди или ответил кто-то, закрываем карточку
            if message.ChannelState in ['5']:
                bitrix_user_id, deafault_user = bitrix.get_user_id(message.CallerIDNum)
                if deafault_user:
                    return
                bitrix.card_action(call_data['bitrix_call_id'], bitrix_user_id, 'hide')


        if message.Context not in HANGUP_DELISTING:

           # Установка статуса звонка, если он еще не установлен
            if 'call_status' not in call_data:
                call_data["call_status"] = dial_status.get(message.Cause, '304')

            # Добавление пользователя по умолчанию если вызов сброшен до регистрации
            if 'bitrix_user_id' not in call_data:
                bitrix_user_id, deafault_user = bitrix.get_user_id(None)
                call_data['bitrix_user_id'] = bitrix_user_id
                bitrix_call_id = bitrix.register_call(bitrix_user_id, call_data['phone_number'], 2)
                call_data['bitrix_call_id'] = bitrix_call_id

            # Закрытие звонка в битрикс
            if bitrix.finish_call(call_data) and call_data["call_status"] == 200:

                # передача записи звонка
                if 'file_patch' not in call_data:
                    return
                file_url = f'{RECORDS_URL}{call_data["file_patch"]}'
                response = requests.get(file_url)
                if response.status_code == 200:
                    encoded_file = base64.b64encode(response.content)

                    bitrix.attachRecord(call_data, encoded_file)

            del calls_data[call_id]
            print(calls_data)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    manager.on_connect = on_connect
    manager.on_login = on_login
    manager.on_disconnect = on_disconnect
    manager.connect(run_forever=True, on_shutdown=on_shutdown)