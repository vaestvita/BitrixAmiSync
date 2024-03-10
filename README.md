# BitrixAmiSync

Протестировано с Asterisk v. 16, 18, 20 (FreePBX) - если названия используемых в фильтрах контекстов, отличаются от используемых в вашей системе - замените их.

Скрипт позволяет отправлять историю звонков и файлы записей из Asterisk (FreePBX) в Битрикс24

Событие OnExternalCallStart (Click 2 Call) с ним работать не будет, необходимо создать локальное приложение [THOTH](https://github.com/vaestvita/thoth)

### Установка 

```
cd /opt
git clone https://github.com/vaestvita/BitrixAmiSync.git
cd BitrixAmiSync
cp config_example.ini config.ini
nano config.ini
```
 
### Заполнить данные в [config.ini](config_example.ini)

Описание параметров [bitrix]
+ [url] - Адрес воходящего вебхука. Интеграции > Rest API > Другое > Входящий вебхук (Необходимые права: crm, user, telephony)
+ [crm_create] - Создавать или нет сущность CRM (1/0)
+ [show_card] - Показывать или нет карточку клиента (1/0)
+ [default_user_id] - ID пользователя по умолчанию для привязки потерянных звонкв. Если параметр не установлен будет использоваться ID первого активного пользователя.

Описание параметров [asterisk]
+ [records_url] - [URL папки](#пример-конфигурации-apache) с записями звонков
+ [host] - адрес ATC
+ [port] - AMI порт
+ [username] - AMI пользователь
+ [secret] - AMI пароль
+ [internal_count] - количество знаков внутренних номеров (для фильтрации)
+ [internal_contexts] - список контекстов внутренних вызовов 
+ [inbound_contexts] - список контекстов внешних вызовов
+ [hangup_delisting] - список контекстов для исключения в событии hangup


### cel_general_custom.conf

```
[general]+
apps=dial
[manager]+
enabled=yes
```

### AMI менеджер bitrixamisync (read CALL, Cdr, dialplan)

/admin/config.php?display=manager

```
[bitrixamisync]
secret = secret
deny=0.0.0.0/0.0.0.0
permit=127.0.0.1/255.255.255.0
read = call,cdr,dialplan
write = 
writetimeout = 100
```

#### Создать службу bitrixamisync 

```
nano /etc/systemd/system/bitrixamisync.service
```
```
[Unit]
Description=BitrixAmiSync

[Service]
ExecStart=/usr/bin/python3 /opt/BitrixAmiSync/app.py
WorkingDirectory=/opt/BitrixAmiSync/
Restart=always
User=nobody
Group=nobody

[Install]
WantedBy=multi-user.target
```
```
fwconsole restart
sudo systemctl daemon-reload
sudo systemctl start bitrixamisync
sudo systemctl enable bitrixamisync
```

### Пример конфигурации Apache 

Конфигурация открывает доступ к файлам записей звонков по адресу http://hostname/monitor

ВНИМАНИЕ - если у вас открыты WWW порты (80, 443), то обязательно настройте ACL, иначе ваши файлы станут всеобщим достоянием

nano /etc/httpd/conf.d/monitor.conf

```
    Alias /monitor /var/spool/asterisk/monitor

    <Directory /var/spool/asterisk/monitor>
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
        IndexOptions FancyIndexing SuppressRules
    </Directory>

```
systemctl restart httpd