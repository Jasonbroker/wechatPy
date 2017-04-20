import requests
import xml.dom.minidom
import json
import time
import re
import os
import subprocess
import random
import multiprocessing
import platform
from collections import defaultdict
import config
import mimetypes
from requests_toolbelt.multipart.encoder import MultipartEncoder


def catchKeyboardInterrupt(fn):
    def wrapper(*args):
        try:
            return fn(*args)
        except KeyboardInterrupt:
            print('\n[*] 强制退出程序')
    return wrapper


def run(word, func, *args):
    print(word)
    if func(*args):
        print('成功')
    else:
        print('失败\n[*] 退出程序')
        exit()


class WebWeixin(object):
    def __str__(self):
        description = \
            "=========================\n" + \
            "[#] Web Weixin\n" + \
            "[#] Debug Mode: " + str(self.DEBUG) + "\n" + \
            "[#] Uuid: " + self.uuid + "\n" + \
            "[#] Uin: " + str(self.uin) + "\n" + \
            "[#] Sid: " + self.sid + "\n" + \
            "[#] Skey: " + self.skey + "\n" + \
            "[#] DeviceId: " + self.deviceId + "\n" + \
            "[#] PassTicket: " + self.pass_ticket + "\n" + \
            "========================="
        return description

    def __init__(self):
        self.session = requests.session()
        self.DEBUG = False
        self.commandLineQRCode = False
        self.uuid = ''
        self.base_uri = ''
        self.redirect_uri = ''
        self.uin = ''
        self.sid = ''
        self.skey = ''
        self.pass_ticket = ''
        self.deviceId = 'e' + repr(random.random())[2:17]
        self.BaseRequest = {}
        self.synckey = ''
        self.SyncKey = []
        self.User = {}
        self.MemberList = []
        self.ContactList = []  # 好友
        self.GroupList = []  # 群
        self.GroupMemeberList = []  # 群友
        self.PublicUsersList = []  # 公众号／服务号
        self.SpecialUsersList = []  # 特殊账号
        self.autoReplyMode = False
        self.syncHost = ''
        self.interactive = False
        self.autoOpen = False
        self.saveFolder = os.path.join(os.getcwd(), 'saved')
        self.saveSubFolders = {'webwxgeticon': 'icons', 'webwxgetheadimg': 'headimgs', 'webwxgetmsgimg': 'msgimgs',
                               'webwxgetvideo': 'videos', 'webwxgetvoice': 'voices', '_showQRCodeImg': 'qrcodes'}
        self.appid = 'wx782c26e4c19acffb'
        self.lang = 'zh_CN'     # en_US
        self.lastCheckTs = time.time()
        self.memberCount = 0
        self.SpecialUsers = ['newsapp','filehelper']
        self.timeout = 20  # 同步最短时间间隔（单位：秒）TODO
        self.media_count = -1
        self.last_chat_user = None

    def load_config(self, configration):
        if configration['DEBUG']:
            self.DEBUG = configration['DEBUG']
        if configration['autoReplyMode']:
            self.autoReplyMode = configration['autoReplyMode']
        if configration['interactive']:
            self.interactive = configration['interactive']

    def getuuid(self):
        url = 'https://login.weixin.qq.com/jslogin'
        params = {
            'appid': self.appid,
            'fun': 'new',
            'lang': self.lang,
            '_': int(time.time()),
        }
        r = self.session.get(url=url, params=params)
        regx = r'window.QRLogin.code = (\d+); window.QRLogin.uuid = "(\S+?)";'   # js
        data = re.search(regx, r.text)
        uuid = None
        if data and data.group(1) == '200':
            uuid = data.group(2)
            print('uuid: %s' % uuid)
        return uuid

    # 获取二维码
    def show_qr_code(self, uuid):
        url = 'https://login.weixin.qq.com/qrcode/' + uuid
        r = self.session.get(url, stream=True)

        with open(config.qr_code, 'wb') as f:
            f.write(r.content)
        # 打开图片
        if platform.system() == 'Darwin':
            subprocess.call(['open', config.qr_code])
        elif platform.system() == 'Linux':
            subprocess.call(['xdg-open', config.qr_code])
        else:
            os.startfile(config.qr_code)

    '''等待二维码刷新'''
    def wait_for_login(self, uuid, tip=1):
        url = 'https://login.weixin.qq.com/cgi-bin/mmwebwx-bin/login'
        payload = {
            'tip': tip,
            'uuid': uuid,
            '_': int(time.time()),
        }

        while True:
            r = self.session.get(url, params=payload)
            print('qr code scaned ' + r.text)

            regx = r'window.code=(\d+)'
            data = re.search(regx, r.text)
            if not data:
                print('no data')
                continue
            status_code = data.group(1)
            if status_code == '200':
                uri_regex = r'window.redirect_uri="(\S+)";'  # 登录后需要重定向的地址
                redirect_uri = re.search(uri_regex, r.text).group(1)
                print('redirect uri: ' + redirect_uri)
                break
            elif status_code == '201':
                print('You have scanned the QRCode, press confirm button on the phone')
                time.sleep(1)
                continue
            elif status_code == '408':
                raise Exception('QRCode should be renewed')     # 二维码过期

        return redirect_uri

    def login(self):
        data = self.session.get(self.redirect_uri, allow_redirects=False)
        if not data.text:
            return False
        doc = xml.dom.minidom.parseString(data.text)
        root = doc.documentElement
        for node in root.childNodes:
            if node.nodeName == 'skey':
                self.skey = node.childNodes[0].data
            elif node.nodeName == 'wxsid':
                self.sid = node.childNodes[0].data
            elif node.nodeName == 'wxuin':
                self.uin = node.childNodes[0].data
            elif node.nodeName == 'pass_ticket':
                self.pass_ticket = node.childNodes[0].data

        if '' in (self.skey, self.sid, self.uin, self.pass_ticket):
            return False
        self.BaseRequest = {
            'Uin': int(self.uin),
            'Sid': self.sid,
            'Skey': self.skey,
            'DeviceID': self.deviceId,
        }
        return True

    # 获取用户的基本信息
    def webwxinit(self):
        url = self.base_uri + '/webwxinit?pass_ticket=%s&skey=%s&r=%s' % (
            self.pass_ticket, self.skey, int(time.time()))
        data = {
            'BaseRequest': self.BaseRequest
        }

        response = self.session.post(url, data=json.dumps(data), headers=config.HEADERS)
        dic = json.loads(response.content.decode('utf-8', 'replace'))
        if not dic:
            return False
        self.SyncKey = dic['SyncKey']
        self.User = dic['User']
        # synckey for synccheck
        self.synckey = '|'.join(
            [str(keyVal['Key']) + '_' + str(keyVal['Val']) for keyVal in self.SyncKey['List']])

        return dic['BaseResponse']['Ret'] == 0

    def webwxstatusnotify(self):
        url = self.base_uri + '/webwxstatusnotify?lang=zh_CN&pass_ticket=%s' % self.pass_ticket
        data = {
            'BaseRequest': self.BaseRequest,
            'Code': 3,
            "FromUserName": self.User['UserName'],
            "ToUserName": self.User['UserName'],
            "ClientMsgId": int(time.time())
        }
        r = self.session.post(url, data=json.dumps(data))
        dic = json.loads(r.content.decode('utf-8', 'replace'))
        if dic == '':
            return False
        print(dic)
        return dic['BaseResponse']['Ret'] == 0

    def webwxgetcontact(self):
        su = self.SpecialUsers
        url = self.base_uri + '/webwxgetcontact?pass_ticket=%s&skey=%s&r=%s' % (
            self.pass_ticket, self.skey, int(time.time()))
        response = self.session.get(url)
        dic = json.loads(response.content.decode('utf-8', 'replace'))
        if dic == '':
            return False

        self.MemberCount = dic['MemberCount']
        self.MemberList = dic['MemberList']
        contactlist = self.MemberList[:]
        print(contactlist)
        for i in range(len(contactlist) - 1, -1, -1):
            contact = contactlist[i]
            if contact['VerifyFlag'] & 8 != 0:  # 公众号/服务号
                contactlist.remove(contact)
                self.PublicUsersList.append(contact)
            elif contact['UserName'] in su:  # 特殊账号
                contactlist.remove(contact)
                self.SpecialUsersList.append(contact)
            elif '@@' in contact['UserName']:  # 群聊
                contactlist.remove(contact)
                self.GroupList.append(contact)
            elif contact['UserName'] == self.User['UserName']:  # 自己
                contactlist.remove(contact)
        self.ContactList = contactlist

        return True

    # TODO
    def webwxbatchgetcontact(self):
        url = self.base_uri + \
              '/webwxbatchgetcontact?type=ex&r=%s&pass_ticket=%s' % (
                  int(time.time()), self.pass_ticket)
        data = {
            'BaseRequest': self.BaseRequest,
            "Count": len(self.GroupList),
            "List": [{"UserName": g['UserName'], "EncryChatRoomId": ""} for g in self.GroupList]
        }
        response = self.session.post(url, data=json.dumps(data))
        dic = json.loads(response.content.decode('utf-8', 'replace'))
        # print('aaaaaaaaaaaaa\n' + response.text)
        if dic == '':
            return False

        # blabla ...
        contactlist = dic['ContactList']
        # ContactCount = dic['Count']
        self.GroupList = contactlist
        for i in range(len(contactlist) - 1, -1, -1):
            contact = contactlist[i]
            ml = contact['MemberList']
            for member in ml:
                self.GroupMemeberList.append(member)
        return True

    def testsynccheck(self):
        synchost = config.synchost
        for host in synchost:
            self.syncHost = host
            [retcode, selector] = self.synccheck()
            # 0 正常 1100 失败/登出微信 selector:
            # 0 正常 2 新的消息
            if retcode == '0':
                return True
            elif retcode == '1100':
                print('重新登录微信')
                exit(0)
        return False

    def synccheck(self):
        params = {
            'r': int(time.time()),
            'sid': self.sid,
            'uin': self.uin,
            'skey': self.skey,
            'deviceid': self.deviceId,
            'synckey': self.synckey,
            '_': int(time.time()),
        }
        url = 'https://' + self.syncHost + '/cgi-bin/mmwebwx-bin/synccheck'
        response = self.session.get(url, params=params)
        data = str(response.content)
        if data == '':
            return [-1, -1]

        pm = re.search(r'window.synccheck={retcode:"(\d+)",selector:"(\d+)"}', data)
        retcode = pm.group(1)
        selector = pm.group(2)
        print('synccheck duration ', response.elapsed)
        return [retcode, selector]

    def webwxsync(self):
        url = self.base_uri + '/webwxsync?sid=%s&skey=%s&pass_ticket=%s' % (
                  self.sid, self.skey, self.pass_ticket)
        datas = {
            'BaseRequest': self.BaseRequest,
            'SyncKey': self.SyncKey,
            'rr': ~int(time.time())
        }
        r = self.session.post(url, data=json.dumps(datas).encode())
        dic = json.loads(r.content.decode('utf-8'))
        if dic == '':
            return None
        # if self.DEBUG:
            # print(json.dumps(dic, indent=4))

        if dic['BaseResponse']['Ret'] == 0:
            self.SyncKey = dic['SyncKey']
            self.synckey = '|'.join(
                [str(keyVal['Key']) + '_' + str(keyVal['Val']) for keyVal in self.SyncKey['List']])
        return dic

    def webwxsendmsg(self, word, to='filehelper'):
        url = self.base_uri + '/webwxsendmsg?pass_ticket=%s' % self.pass_ticket
        params = {
            'BaseRequest': self.BaseRequest,
            'Msg': {
                "Type": 1,
                "Content": self.transcoding(word),
                "FromUserName": self.User['UserName'],
                "ToUserName": to,
                "LocalID": str(int(time.time() * 1000000)),
                "ClientMsgId": str(int(time.time() * 1000000))
            }
        }
        data = json.dumps(params, ensure_ascii=False).encode('utf8')
        r = requests.post(url, data=data, headers=config.HEADERS)
        dic = r.json()
        return dic['BaseResponse']['Ret'] == 0 # 发送成功

    # TODO
    def webwxrevokemsg(self, user_id, msg_id):
        pass

    def webwxuploadmedia(self, image_name):
        url = 'https://file2.wx.qq.com/cgi-bin/mmwebwx-bin/webwxuploadmedia?f=json'
        # 计数器
        self.media_count += 1
        # 文件名
        file_name = image_name
        # MIME格式
        # mime_type = application/pdf, image/jpeg, image/png, etc.
        mime_type = mimetypes.guess_type(image_name, strict=False)[0]
        # 微信识别的文档格式，微信服务器应该只支持两种类型的格式。pic和doc
        # pic格式，直接显示。doc格式则显示为文件。
        media_type = 'pic' if mime_type.split('/')[0] == 'image' else 'doc'
        # 上一次修改日期
        lastModifieDate = 'Thu Mar 17 2017 00:55:10 GMT+0800 (CST)'
        # 文件大小
        file_size = os.path.getsize(file_name)
        # PassTicket
        pass_ticket = self.pass_ticket
        # clientMediaId
        client_media_id = str(int(time.time() * 1000000))
        # webwx_data_ticket
        webwx_data_ticket = ''
        for item in self.session.cookies:
            if item.name == 'webwx_data_ticket':
                webwx_data_ticket = item.value
                break
        if (webwx_data_ticket == ''):
            return "No Cookie"

        uploadmediarequest = json.dumps({
            "BaseRequest": self.BaseRequest,
            "ClientMediaId": client_media_id,
            "TotalLen": file_size,
            "StartPos": 0,
            "DataLen": file_size,
            "MediaType": 4
        }, ensure_ascii=False).encode('utf8')

        multipart_encoder = MultipartEncoder(
            fields={
                'id': 'WU_FILE_' + str(self.media_count),
                'name': file_name,
                'type': mime_type,
                'lastModifieDate': lastModifieDate,
                'size': str(file_size),
                'mediatype': media_type,
                'uploadmediarequest': uploadmediarequest,
                'webwx_data_ticket': webwx_data_ticket,
                'pass_ticket': pass_ticket,
                'filename': (file_name, open(file_name, 'rb'), mime_type.split('/')[1])
            },
            boundary='-----------------------------1575017231431605357584454111'
        )

        headers = {
            'Host': 'file2.wx.qq.com',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.10; rv:42.0) Gecko/20100101 Firefox/42.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://wx2.qq.com/',
            'Content-Type': multipart_encoder.content_type,
            'Origin': 'https://wx2.qq.com',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'
        }

        r = requests.post(url, data=multipart_encoder, headers=headers)
        response_json = r.json()
        if response_json['BaseResponse']['Ret'] == 0:
            return response_json
        return None

    def webwxsendmsgimg(self, user_id, media_id):
        url = 'https://wx2.qq.com/cgi-bin/mmwebwx-bin/webwxsendmsgimg?fun=async&f=json&pass_ticket=%s' % self.pass_ticket
        clientMsgId = str(int(time.time() * 1000000))
        data_json = {
            "BaseRequest": self.BaseRequest,
            "Msg": {
                "Type": 3,
                "MediaId": media_id,
                "FromUserName": self.User['UserName'],
                "ToUserName": user_id,
                "LocalID": clientMsgId,
                "ClientMsgId": clientMsgId
            }
        }
        headers = {'content-type': 'application/json; charset=UTF-8'}
        data = json.dumps(data_json, ensure_ascii=False).encode('utf8')
        r = requests.post(url, data=data, headers=headers)
        dic = r.json()
        return dic['BaseResponse']['Ret'] == 0

    def webwxsendmsgemotion(self, user_id, media_id):
        url = 'https://wx2.qq.com/cgi-bin/mmwebwx-bin/webwxsendemoticon?fun=sys&f=json&pass_ticket=%s' % self.pass_ticket
        clientMsgId = str(int(time.time() * 1000000))
        data_json = {
            "BaseRequest": self.BaseRequest,
            "Msg": {
                "Type": 47,
                "EmojiFlag": 2,
                "MediaId": media_id,
                "FromUserName": self.User['UserName'],
                "ToUserName": user_id,
                "LocalID": clientMsgId,
                "ClientMsgId": clientMsgId
            }
        }
        headers = {'content-type': 'application/json; charset=UTF-8'}
        data = json.dumps(data_json, ensure_ascii=False).encode('utf8')
        r = requests.post(url, data=data, headers=headers)
        dic = r.json()
        if self.DEBUG:
            print(json.dumps(dic, indent=4))
        return dic['BaseResponse']['Ret'] == 0

    def webwxgeticon(self, someid):
        url = self.base_uri + \
              '/webwxgeticon?username=%s&skey=%s' % (id, self.skey)
        r = self.session.get(url)
        data = r.content
        if data == '':
            return ''
        fn = 'img_' + someid + '.jpg'
        return self._saveFile(fn, data, 'webwxgeticon')

    def webwxgetheadimg(self, someid):
        url = self.base_uri + \
              '/webwxgetheadimg?username=%s&skey=%s' % (someid, self.skey)
        r = self.session.get(url, stream=True)
        data = r.content
        if data:
            return ''
        fn = 'img_' + someid + '.jpg'
        return self._saveFile(fn, data, 'webwxgetheadimg')

    def webwxgetmsgimg(self, msgid):
        url = self.base_uri + \
              '/webwxgetmsgimg?MsgID=%s&skey=%s' % (msgid, self.skey)
        r = self.session.get(url, stream=True)
        data = r.content
        if data == '':
            return ''
        fn = 'img_' + msgid + '.jpg'
        return self._saveFile(fn, data, 'webwxgetmsgimg')

    # FIXME
    def webwxgetvideo(self, msgid):
        pass

    def webwxgetvoice(self, msgid):
        url = self.base_uri + \
              '/webwxgetvoice?msgid=%s&skey=%s' % (msgid, self.skey)
        header = dict()
        header['Range'] = 'bytes=0-'
        r = self.session.get(url, headers=header)
        data = r.content
        if data == '':
            return ''
        fn = 'voice_' + msgid + '.mp3'
        return self._saveFile(fn, data, 'webwxgetvoice')

    def getNameById(self, id):
        url = self.base_uri + '/webwxbatchgetcontact?type=ex&r=%s&pass_ticket=%s' % (
                  int(time.time()), self.pass_ticket)
        params = {
            'BaseRequest': self.BaseRequest,
            "Count": 1,
            "List": [{"UserName": id, "EntryChatRoomId": ""}]
        }
        r = self.session.post(url, params=json.dumps(params))
        dic = json.loads(r.content.decode('utf-8', 'replace'))
        if dic == '':
            return None
        return dic['ContactList']

    def getGroupName(self, id):
        name = '未知群'
        for member in self.GroupList:
            if member['UserName'] == id:
                name = member['NickName']
        if name == '未知群':
            # 现有群里面查不到
            GroupList = self.getNameById(id)
            for group in GroupList:
                self.GroupList.append(group)
                if group['UserName'] == id:
                    name = group['NickName']
                    MemberList = group['MemberList']
                    for member in MemberList:
                        self.GroupMemeberList.append(member)
        return name

    def getUserRemarkName(self, username):
        name = '未知群' if username[:2] == '@@' else '陌生人'
        if username == self.User['UserName']:
            return self.User['NickName']  # 自己

        if username[:2] == '@@':
            # 群
            name = self.getGroupName(username)
        else:
            # 特殊账号
            for member in self.SpecialUsersList:
                if member['UserName'] == username:
                    name = member['RemarkName'] if member[
                        'RemarkName'] else member['NickName']

            # 公众号或服务号
            for member in self.PublicUsersList:
                if member['UserName'] == username:
                    name = member['RemarkName'] if member[
                        'RemarkName'] else member['NickName']

            # 直接联系人
            for member in self.ContactList:
                if member['UserName'] == username:
                    name = member['RemarkName'] if member[
                        'RemarkName'] else member['NickName']
            # 群友
            for member in self.GroupMemeberList:
                if member['UserName'] == username:
                    name = member['DisplayName'] if member[
                        'DisplayName'] else member['NickName']

        if name == '未知群' or name == '陌生人':
            print(username)
        return name

    # 获取发送是使用的名字
    def get_username_from_readable_name(self, name):
        for member in self.MemberList:
            if name == member['RemarkName'] or name == member['NickName']:
                return member['UserName']
        return None

    def _showMsg(self, message):
        # 地理位置，群消息，红包消息等类型的打印
        pass

    def handleMsg(self, msg_list):
        for msg in msg_list['AddMsgList']:
            if self.DEBUG:
                fn = 'msg_' + str(time.time()) + '.json'
                with open(fn, 'w') as f:
                    f.write(json.dumps(msg))
                # print('[*] 该消息已储存到文件: %s' % fn)

            msgType = msg['MsgType']
            name = self.getUserRemarkName(msg['FromUserName'])
            content = msg['Content'].replace('&lt;', '<').replace('&gt;', '>')
            # 消息类型
            msgid = msg['MsgId']

            '''
            if self.autoReplyMode:
                # 小冰
                self.xiaobingautohandle(content, msgid, msgType, nick_name=name)
                return
            '''
            if msgType == 1:
                raw_msg = {'raw_msg': msg}
                self._showMsg(raw_msg)
                #'''# 图灵机器人
                if self.autoReplyMode:
                    # 机器人自动回复
                    ans = self.send_to_tuling(content, user_id=msg['FromUserName']) + '\n[来自微信机器人]'
                    if self.webwxsendmsg(ans, msg['FromUserName']):
                        print('自动回复: ===========\n' + ans + '\n==================')
                    else:
                        print('自动回复失败')
                #'''
            elif msgType == 3:
                image = self.webwxgetmsgimg(msgid)
                raw_msg = {'raw_msg': msg,
                           'message': '%s 发送了一张图片: %s' % (name, image)}
                self._showMsg(raw_msg)
                self._safe_open(image)
            elif msgType == 34:
                voice = self.webwxgetvoice(msgid)
                raw_msg = {'raw_msg': msg,
                           'message': '%s 发了一段语音: %s' % (name, voice)}
                self._showMsg(raw_msg)
                self._safe_open(voice)
            elif msgType == 42:
                raw_msg = {'raw_msg': msg, 'message': '%s 发送了一张名片: %s' % (
                    name.strip(), json.dumps(info))}
                self._showMsg(raw_msg)

                info = msg['RecommendInfo']
                print('%s 发送了一张名片:' % name)
                print('=========================')
                print('= 昵称: %s' % info['NickName'])
                print('= 微信号: %s' % info['Alias'])
                print('= 地区: %s %s' % (info['Province'], info['City']))
                print('= 性别: %s' % ['未知', '男', '女'][info['Sex']])
                print('=========================')
            elif msgType == 47:     # 暂不支持内置表情
                url = self._searchContent('cdnurl', content)
                raw_msg = {'raw_msg': msg,
                           'message': '%s 发了一个动画表情，点击下面链接查看: %s' % (name, url)}
                self._showMsg(raw_msg)
                self._safe_open(url)
            elif msgType == 49:
                appMsgType = defaultdict(lambda: "")
                appMsgType.update({5: '链接', 3: '音乐', 7: '微博'})
                print('%s 分享了一个%s:' % (name, appMsgType[msg['AppMsgType']]))
                print('=========================')
                print('= 标题: %s' % msg['FileName'])
                print('= 描述: %s' % self._searchContent('des', content, 'xml'))
                print('= 链接: %s' % msg['Url'])
                print('= 来自: %s' % self._searchContent('appname', content, 'xml'))
                print('=========================')
                card = {
                    'title': msg['FileName'],
                    'description': self._searchContent('des', content, 'xml'),
                    'url': msg['Url'],
                    'appname': self._searchContent('appname', content, 'xml')
                }
                raw_msg = {'raw_msg': msg, 'message': '%s 分享了一个%s: %s' % (
                    name, appMsgType[msg['AppMsgType']], json.dumps(card))}
                self._showMsg(raw_msg)
            elif msgType == 51:
                raw_msg = {'raw_msg': msg, 'message': '[*] 成功获取联系人信息'}
                self._showMsg(raw_msg)
            # FIXME
            elif msgType == 62:
                video = self.webwxgetvideo(msgid)
                raw_msg = {'raw_msg': msg,
                           'message': '%s 发了一段小视频: %s' % (name, video)}
                self._showMsg(raw_msg)
                self._safe_open(video)
            elif msgType == 10002:
                raw_msg = {'raw_msg': msg, 'message': '%s 撤回了一条消息' % name}
                self._showMsg(raw_msg)
            else:
                print('[*] 未知的消息类型: %d: %s' % (msgType, json.dumps(msg)))
                raw_msg = {
                    'raw_msg': msg, 'message': '[*] 未知的消息类型: %d' % msgType}
                self._showMsg(raw_msg)

    def listenMsgMode(self):
        print('[*] 进入消息监听模式 ... 成功')
        run('[*] 线路测试 ... ', self.testsynccheck)
        playWeChat = 0
        redEnvelope = 0
        while True:
            self.lastCheckTs = time.time()
            [retcode, selector] = self.synccheck()
            if self.DEBUG:
                date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                print('%s retcode: %s, selector: %s' % (date, retcode, selector))
            if retcode == '1100':
                print('[*] 你在手机上登出了微信')
                break
            if retcode == '1101':
                print('[*] 你在其他地方登录了 WEB 版微信')
                break
            elif retcode == '0':
                if selector == '2':
                    r = self.webwxsync()
                    if r is not None:
                        self.handleMsg(r)
                elif selector == '6':
                    # TODO
                    redEnvelope += 1
                    print('[*] 收到红包消息 %d 次' % redEnvelope)
                elif selector == '7':
                    playWeChat += 1
                    print('[*] 手机玩微信 %d 次' % playWeChat)
                elif selector == '0':
                    time.sleep(1)
            if (time.time() - self.lastCheckTs) <= 10:
                time.sleep(time.time() - self.lastCheckTs)

    def sendMsg(self, name, word, isfile=False):
        uid = self.get_username_from_readable_name(name)
        if id:
            if isfile:
                with open(word, 'r') as f:
                    for line in f.readlines():
                        line = line.replace('\n', '')
                        print('-> ' + name + ': ' + line)
                        if self.webwxsendmsg(line, uid):
                            print(' [成功]')
                        else:
                            print(' [失败]')
                        time.sleep(1)
            else:
                if self.webwxsendmsg(word, uid):
                    print('[*] 消息发送成功')
                else:
                    print('[*] 消息发送失败')
        else:
            print('[*] 此用户不存在')

    def sendMsgToAll(self, word):
        for contact in self.ContactList:
            name = contact['RemarkName'] if contact[
                'RemarkName'] else contact['NickName']
            username = contact['UserName']
            print('-> ' + name + ': ' + word)
            if self.webwxsendmsg(word, username):
                print(' [成功]')
            else:
                print(' [失败]')
            time.sleep(1)

    def sendImg(self, name, file_name):
        response = self.webwxuploadmedia(file_name)
        media_id = ""
        if response is not None:
            media_id = response['MediaId']
        user_id = self.get_username_from_readable_name(name)
        response = self.webwxsendmsgimg(user_id, media_id)
        return response

    def sendEmotion(self, name, file_name):
        response = self.webwxuploadmedia(file_name)
        media_id = ""
        if response is not None:
            media_id = response['MediaId']
        user_id = self.getUserID(name)
        response = self.webwxsendmsgemotion(user_id, media_id)
        return response

    @catchKeyboardInterrupt
    def start(self):
        print('[*] 微信 ... 正在启动')
        print('[*] 正在获取 uuid ...')
        self.uuid = self.getuuid()
        print('[*] 正在获取二维码')
        self.show_qr_code(uuid=self.uuid)
        print('[*] 请使用微信扫描二维码以登录 ... ')

        self.redirect_uri = self.wait_for_login(uuid=self.uuid)
        self.base_uri = self.redirect_uri[:self.redirect_uri.rfind('/')]

        print('[*] 正在登录 ...')
        self.login()
        print('[*] 微信初始化 ... ')
        self.webwxinit()
        print('[*] 开启状态通知 ... ')
        self.webwxstatusnotify()
        print('[*] 获取联系人 ... ')
        self.webwxgetcontact()
        print('[*] 应有 %s 个联系人，读取到联系人 %d 个' % (self.MemberCount, len(self.MemberList)))
        print('[*] 共有 %d 个群 | %d 个直接联系人 | %d 个特殊账号 ｜ %d 公众号或服务号' % (len(self.GroupList),
                                                                         len(self.ContactList),
                                                                         len(self.SpecialUsersList),
                                                                         len(self.PublicUsersList)))
        print('[*] 批量获取contacts ... ')
        self.webwxbatchgetcontact()
        print('[*] 微信 ... 启动完成\n')
        print(self)

        if not self.autoReplyMode:
            if self.interactive and input('[*] 是否开启自动回复模式(y/n): ') == 'y':
                self.autoReplyMode = True
                print('[*] 自动回复模式 ... 开启')
            else:
                print('[*] 自动回复模式 ... 关闭')

        # if sys.platform.startswith('win'):
        #     import _thread
        #     _thread.start_new_thread(self.listenMsgMode())
        # else:
        #     listenProcess = multiprocessing.Process(target=self.listenMsgMode)
        #     listenProcess.start()

        listen_process = multiprocessing.Process(target=self.listenMsgMode)
        listen_process.start()

        while True:
            text = input('请输入命令$: ')
            if text == 'quit':
                listen_process.terminate()
                print('[*] 退出微信')
                exit(0)
            elif text[:2] == '->':
                [name, word] = text[2:].split(':')
                if name == 'all':
                    self.sendMsgToAll(word)  # '->all:你好'
                else:
                    self.sendMsg(name, word)    # '->若鱼:你好'
            elif text[:3] == 'f->':
                print('发送文件')
                [name, file] = text[3:].split(':')
                self.sendMsg(name, file, True)
            elif text[:3] == 'i->':
                print('发送图片')
                [name, file_name] = text[3:].split(':')
                self.sendImg(name, file_name)
            elif text[:3] == 'e->':
                print('发送表情')
                [name, file_name] = text[3:].split(':')
                self.sendEmotion(name, file_name)
            # TODO 发送语音视频

    def _safe_open(self, path):
        if self.autoOpen:
            if platform.system() == "Linux":
                os.system("xdg-open %s &" % path)
            else:
                os.system('open %s &' % path)

    # 保存文件
    def _saveFile(self, filename, data, api=None):
        fn = filename
        if self.saveSubFolders[api]:
            dirName = os.path.join(self.saveFolder, self.saveSubFolders[api])
            if not os.path.exists(dirName):
                os.makedirs(dirName)
            fn = os.path.join(dirName, filename)
            with open(fn, 'wb') as f:
                f.write(data)
                f.close()
        return fn

    def transcoding(self, data):
        if not data:
            return data
        result = None
        if type(data) == str:
            result = data
        elif type(data) == bytes:
            result = data.decode('utf-8')
        return result

    # 机器人
    def send_to_tuling(self, msg, user_id):
        api_key = '42824c30e972429f9ec99028bf71f1ce'
        url = 'http://www.tuling123.com/openapi/api'  # http://www.tuling123.com
        payloads = {
            'key': api_key,
            'user_id': str(user_id),
            'info': msg
            }
        r = self.session.post(url, data=payloads)
        dic = r.json()
        return dic.get('text', '…………')

    # 小冰
    def xiaobingautohandle(self, content, msgid, msgtype, nick_name):
        if nick_name == '小冰':
            self.replay_from_xiaobing(content, msgid, msgtype, forwordto=self.last_chat_user)
        else:
            self.last_chat_user = nick_name
            self.send_to_xiaobing(content, msgid, msgtype, nick_name)

    def send_to_xiaobing(self, msg, msgid, msgtype, user):
        xiaobing = self.get_username_from_readable_name('小冰')
        if msgtype == 1:
            self.webwxsendmsg(msg, xiaobing)
        elif msgtype == 3:
            image = self.webwxgetmsgimg(msgid)
            dic = self.webwxuploadmedia(image)
            mediaid = dic['MediaId']
            self.webwxsendmsgimg(xiaobing, media_id=mediaid)
        else:
            print('很可惜没有的功能')

    def replay_from_xiaobing(self, msg, msgid, msgtype, forwordto):
        forworduser = self.get_username_from_readable_name(forwordto)
        if msgtype == 1:
            word = msg + '\n[由小冰回复]'
            self.webwxsendmsg(word, forworduser)
        elif msgtype == 3:
            image = self.webwxgetmsgimg(msgid)
            dic = self.webwxuploadmedia(image)
            mediaid = dic['MediaId']
            self.webwxsendmsgimg(forworduser, media_id=mediaid)
        elif msgtype == 34:
            print('很可惜没有发送语音的功能')

    # TODO cache login info and login automatically during short time

if __name__ == '__main__':

        webwx = WebWeixin()
        webwx.load_config({'interactive': True, 'DEBUG': True, 'autoReplyMode': True})
        webwx.autoOpen = True   # 自动打开图片
        webwx.start()
