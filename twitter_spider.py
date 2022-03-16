import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from configure import configure


class twitter_spider:
    def __init__(self, con, cur, user_list):
        chrome_options = Options()
        # chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        service = Service(executable_path=ChromeDriverManager().install())
        self.browser = webdriver.Chrome(service=service, options=chrome_options)
        self.browser.get("https://twitter.com")
        try:
            with open('cookies.json', 'r', encoding='utf8') as f:
                listCookies = json.loads(f.read())
            for cookie in listCookies:
                self.browser.add_cookie(cookie)
        except Exception:
            print("未登录 请在浏览器当前页面登录账号后按enter键 (cookie仅在本地存储， 不会上传到云端或者什么东西。此代码已开源，请放心使用)")
            input()
            with open('cookies.json', 'w', encoding='utf8') as f:
                listCookies = self.browser.get_cookies()
                json.dump(listCookies, f)
                print("更新完成")
        self.user_list = user_list
        self.config = configure()
        self.twitter_link = "https://twitter.com/"
        self.con = con
        self.cur = cur
        self.message = []

    def process(self):
        for follow in self.user_list:
            temp_link = self.twitter_link + follow
            self.browser.get(temp_link)
            time.sleep(5)
            try:
                self.browser.find_element(by=By.CSS_SELECTOR, value="a[href*=media]").click()
                time.sleep(2)
            except Exception:
                pass
            elements = self.browser.find_elements(by=By.CSS_SELECTOR, value="div.css-1dbjc4n > a")
            ids = []
            links = []
            for element in elements:
                try:
                    element.find_element(by=By.TAG_NAME, value='img').get_attribute('src')
                except Exception as e:
                    continue
                temp = element.get_attribute("href")
                if temp.__contains__("status"):
                    id = temp[temp.find('status/') + 7:temp.find('status/') + 26]
                    if id not in ids:
                        ids.append(id)
                        links.append(temp)
            for id in ids:
                self.cur.execute("select * from data where status_id=%d" % int(id))
                print(id)
                if self.cur.fetchone():
                    print("already have")
                else:
                    self.cur.execute("INSERT INTO data (user, status_id) values (\'%s\', %d)" % (follow, int(id)))
                    self.con.commit()
                    self.message.append(self.twitter_link + follow + '/status/' + id)
            self.cur.execute("UPDATE follow_user SET last_time=%lf WHERE user_name=\'%s\'" % (time.time(), follow))
            self.con.commit()

        self.browser.close()
        return self.message

