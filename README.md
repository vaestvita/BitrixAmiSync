# BitrixAmiSync

Протестирвоано с Asterisk v. 18, 20 (FreePBX) - если навзания используемых в фильтрах контектов, отличаются от используемых в вашей системе - замените их.

Скрипт позволяет отправлять историю звонков и файлы записей из Asterisk (FreePBX) в Битрикс24

Событие OnExternalCallStart (Click 2 Coll) с ним работать не будет, необходимо создать локальное приложение [THOTH](https://github.com/vaestvita/thoth)
 
Заполнить данные в config.ini


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
ExecStart=/usr/bin/python3 /home/api/bitrixamisync.py
WorkingDirectory=/home/api/
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