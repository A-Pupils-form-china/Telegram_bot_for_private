import sqlite3
import time
from threading import Thread
import requests
from telegram.ext import Updater, CommandHandler

import configure
from twitter_spider import twitter_spider


class lion_bot:
    def __init__(self):
        temp = configure.configure()
        self.update_amount = temp.update_amount
        self.update_gap = temp.update_gap
        self.last_update_time = 0

        TOKEN = temp.TOKEN
        self.MY_CHAT_ID = temp.MY_CHAT_ID

        self.updater = Updater(TOKEN)
        self.updater.dispatcher.add_handler(CommandHandler("status", self.status))
        self.updater.dispatcher.add_handler(CommandHandler('run', self.run))
        self.updater.dispatcher.add_handler(CommandHandler('add_follow_user', self.add_follow_user))
        self.updater.dispatcher.add_handler(CommandHandler('get_follow_user', self.get_follow_user))
        self.updater.dispatcher.add_handler(CommandHandler('get_follow_user_length', self.get_follow_user_length))
        self.updater.dispatcher.add_handler(CommandHandler('get_update_queue_user', self.get_update_queue_user))
        self.updater.dispatcher.add_handler(CommandHandler('delete_follow_user', self.delete_follow_user))
        self.updater.dispatcher.add_handler(CommandHandler('set_update_amount', self.set_update_amount))
        self.updater.dispatcher.add_handler(CommandHandler('set_update_gap', self.set_update_gap))

        self.messages = []  # 每条消息的状态
        self.update_user = False  # 更新链接
        self.check_update_user = False  # 获取更新用户的队列
        self.activity_messages = []  # 单次发送的链接
        self.sql_task = []  # 需要执行的sql语句
        self.bot = self.updater.bot  # bot
        self.new_user = []  # 需要添加进数据库的用户
        self.follow_list = []  # 关注列表
        self.update_list = []  # 更新列表
        self.con = None
        self.cur = None
        self.next_time = None
        self.thread_1 = Thread(target=self.con_thread, name="con_thread")
        self.thread_1.start()
        self.updater.start_polling()
        self.updater.idle()

    #  主线程
    def con_thread(self):
        self.con = sqlite3.connect("twitter.sqlite")
        self.cur = self.con.cursor()
        self.cur.execute("SELECT user_name FROM follow_user")
        temp = self.cur.fetchall()
        for i in temp:
            self.follow_list.append(i[0])
        while True:
            self.update_list = self._get_update_queue()
            if self.update_list is not None:
                if self.next_time is None:
                    self.cur.execute("SELECT last_time FROM follow_user")
                    temp = self.cur.fetchall()
                    last_time = []
                    for i in temp:
                        last_time.append(i[0])
                    last_time.sort()
                    self.cur.execute("SELECT count(user_name) FROM follow_user")
                    amount = int(self.cur.fetchone()[0])
                    print()
                    self.next_time = last_time[self.update_amount - 1 if self.update_amount < amount else amount - 1] + self.update_gap * 3600
                elif time.time() > self.next_time or self.update_user:
                    if time.time() - self.last_update_time > 600:
                        self.update_link()
                        self.update_user = False
                        self.next_time = None
                    elif self.update_user:
                        self._send_message_to_me("更新频率太高， 距离下次更新时间还有:" +
                                                 str(int((time.time() - self.last_update_time)) / 60) + "分钟")
                        self.update_user = False
            if len(self.sql_task) > 0:
                for i in range(len(self.sql_task)):
                    try:
                        self.cur.execute(self.sql_task[i])
                    except Exception as e:
                        print(e)
                        print(i)
                self.sql_task = []
            self.con.commit()
            time.sleep(10)

    # 命令

    def add_follow_user(self, update, context):
        if update.effective_chat.id == self.MY_CHAT_ID:
            try:
                message = update.message.text.strip()
                user = message.split(' ')[1]
                result = self._add_follow_user(user)
                self.next_time = None
            except Exception:
                result = "添加失败，格式错误"
            update.message.reply_text(result)

    def delete_follow_user(self, update, context):
        if update.effective_chat.id == self.MY_CHAT_ID:
            result = ''
            try:
                user = update.message.text.split(' ')[1]
            except Exception:
                result = '删除失败， 格式错误'
                update.message.reply_text(result)
                return
            if user in self.follow_list:
                del self.follow_list[self.follow_list.index(user)]
                self.sql_task.append("DELETE FROM follow_user WHERE user_name=\'%s\'" % user)
                result = '删除 %s 成功' % user
            else:
                result = '删除失败， 关注画师中不存在该画师'
            update.message.reply_text(result)

    def get_follow_user(self, update, context):
        result = '关注画师:\n'
        for i in self.follow_list:
            result += i + '\n'
        update.message.reply_text(result)

    def get_follow_user_length(self, update, context):
        update.message.reply_text('已关注画师数量:%d' % len(self.follow_list))

    def get_update_queue_user(self, update, context):
        result = '更新队列:\n'
        if self.update_list:
            for i in self.update_list:
                result += i + '\n'
            update.message.reply_text(result)
        else:
            update.message.reply_text("更新队列为空")

    def run(self, update, context):
        if update.effective_chat.id == self.MY_CHAT_ID:
            if not self.update_user:
                self.update_user = True
                try:
                    self.update_amount = int(update.message.text.split(' ')[1])
                except Exception:
                    update.message.reply_text(
                        "没有输入更新数量，默认值为:%d" % self.update_amount)
            else:
                update.message.reply_text("已经在爬了")

    def status(self, update, context):
        next_time = ''
        if self.next_time is not None:
            next_time = time.strftime("%m-%d %H:%M:%S",
                                      time.localtime(self.next_time + configure.configure().time_gap * 3600))
        else:
            next_time = "获取中"
        update.message.reply_text("我在\n每次更新数量:%d \n更新间隔:%d\n下次更新时间： %s"
                                  % (self.update_amount, self.update_gap, next_time))

    def update_link(self):
        if self.update_list:
            if len(self.update_list) > 0:
                result = '开始更新， 更新队列为:\n'
                for i in self.update_list:
                    result += i + '\n'
                message = twitter_spider(self.con, self.cur, self.update_list).process()
                self.update_list = None
                for i in message:
                    self._send_message_to_me(i)
                self._send_message_to_me("更新完成")
                self.next_time = None
                self.last_update_time = time.time()
        else:
            self._send_message_to_me("没有需要更新的链接")

    def set_update_gap(self, update, context):
        if update.effective_chat.id == self.MY_CHAT_ID:
            try:
                update_gap = int(update.message.text.split(' ')[1])
            except Exception:
                self._send_message_to_me("设置更新间隔失败， 格式错误")
                return
            self.update_gap = update_gap
            self.next_time = None
            self._send_message_to_me("设置更新间隔成功， 间隔为 %d 小时" % self.update_gap)

    def set_update_amount(self, update, context):
        if update.effective_chat.id == self.MY_CHAT_ID:
            try:
                update_amount = int(update.message.text.split(" ")[1])
            except Exception:
                self._send_message_to_me("设置每次更新数量失败， 格式错误")
                return
            self.update_amount = update_amount
            self._send_message_to_me("设置更新数量成功，  %d" % self.update_amount)

    # 内部调用函数

    def _get_update_queue(self):
        last_time = time.time() - self.update_gap * 3600
        self.cur.execute("SELECT user_name FROM follow_user WHERE last_time<%lf" % last_time)
        temp = self.cur.fetchall()
        if len(temp) > 0:
            temp = temp[:self.update_amount]
            update_list = []
            for i in temp:
                update_list.append(i[0])
            return update_list
        else:
            return None

    def _send_message_to_me(self, text):
        self.bot.send_message(chat_id=self.MY_CHAT_ID, text=text)

    def _add_follow_user(self, user):
        result = ''
        if user in self.follow_list:
            result = '数据库已存在该画师'
            return result
        result_code = requests.get("https://twitter.com/" + user).status_code
        if result_code == 200:
            self.follow_list.append(user)
            self.sql_task.append("INSERT INTO follow_user (user_name, last_time) values (\'%s\', 0)" % user)
            result = "添加画师 %s 成功" % user
        else:
            result = "添加失败，该画师空间无法直接被访问"
        self.next_time = None
        return result


lion_bot()
