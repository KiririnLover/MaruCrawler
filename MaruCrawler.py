import os
import sys
import time
import configparser
import multiprocessing
import urllib.request

from urllib.parse import quote
from bs4 import *
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

from ImageDownloader import *
from Utils import *

# Module multiprocessing is organized differently in Python 3.4+
try:
    # Python 3.4+
    if sys.platform.startswith('win'):
        import multiprocessing.popen_spawn_win32 as forking
    else:
        import multiprocessing.popen_fork as forking
except ImportError:
    import multiprocessing.forking as forking

if sys.platform.startswith('win'):
    # First define a modified version of Popen.
    class _Popen(forking.Popen):
        def __init__(self, *args, **kw):
            if hasattr(sys, 'frozen'):
                # We have to set original _MEIPASS2 value from sys._MEIPASS
                # to get --onefile mode working.
                os.putenv('_MEIPASS2', sys._MEIPASS)
            try:
                super(_Popen, self).__init__(*args, **kw)
            finally:
                if hasattr(sys, 'frozen'):
                    # On some platforms (e.g. AIX) 'os.unsetenv()' is not
                    # available. In those cases we cannot delete the variable
                    # but only set it to the empty string. The bootloader
                    # can handle this case.
                    if hasattr(os, 'unsetenv'):
                        os.unsetenv('_MEIPASS2')
                    else:
                        os.putenv('_MEIPASS2', '')

    # Second override 'Popen' class with our modified version.
    forking.Popen = _Popen

class MaruCrawler():
    def __init__(self, processNum = 4):
        self.version = "2.00"
        self.logger = CreateLogger("MaruCrawler")
        self.processNum = processNum
        self.driverPath = os.path.realpath('phantomjs.exe')
        self.opener = urllib.request.build_opener()
        self.opener.addheaders = [('User-Agent', "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.116 Safari/537.36")]
        self.mainURL = "http://marumaru.in/b/mangaup/"

    def PrintBanner(self):
        banner = """
 __       __                                 ______                                    __
|  \     /  \                               /      \                                  |  \\
| $$\   /  $$  ______    ______   __    __ |  $$$$$$\  ______   ______   __   __   __ | $$  ______    ______
| $$$\ /  $$$ |      \  /      \ |  \  |  \| $$   \$$ /      \ |      \ |  \ |  \ |  \\| $$ /      \\  /      \\
| $$$$\  $$$$  \$$$$$$\|  $$$$$$\| $$  | $$| $$      |  $$$$$$\ \$$$$$$\| $$ | $$ | $$| $$|  $$$$$$\|  $$$$$$\\
| $$\$$ $$ $$ /      $$| $$   \$$| $$  | $$| $$   __ | $$   \$$/      $$| $$ | $$ | $$| $$| $$    $$| $$   \$$
| $$ \$$$| $$|  $$$$$$$| $$      | $$__/ $$| $$__/  \| $$     |  $$$$$$$| $$_/ $$_/ $$| $$| $$$$$$$$| $$
| $$  \$ | $$ \$$    $$| $$       \$$    $$ \$$    $$| $$      \$$    $$ \$$   $$   $$| $$ \$$     \| $$
 \$$      \$$  \$$$$$$$ \$$        \$$$$$$   \$$$$$$  \$$       \$$$$$$$  \$$$$$\$$$$  \$$  \$$$$$$$ \$$

                                                                                                     %s ver.""" % (self.version)
        print(banner)

    def Run(self, mangaNumber):
        # Check files
        if not os.path.exists(self.driverPath):
            self.logger.error("WebDriverNotFound ( path : %s )" % (self.driverPath))
            return False

        self.mangaNumber = mangaNumber
        self.mangaURL    = self.mainURL + str(self.mangaNumber)
        self.logger.debug("Start Crawling %d" % (self.mangaNumber))

        # Get Manga main source
        source = self.Crawl(self.mangaURL)
        if source == False:
            return False
        # Get Manga name
        source = BeautifulSoup(source, "html5lib")
        self.manga = source.find('div', {'class': 'subject'})
        if self.manga == None:
            self.logger.error("CannotFindManga ( url : %s )" % (self.mangaURL))
            return False
        self.manga = "[%d] %s" % (self.mangaNumber, self.manga.text.strip())
        self.manga = ValidateFileName(self.manga)
        self.logger.info("Manga name : %s" % self.manga)
        # Get Manga Episodes
        self.episodeLists = self.GetEpisodeLists(source)
        if len(self.episodeLists) == 0:
            self.logger.error("NoEpisodes ( url : %s )" % (self.mangaURL))
            return False

        # Make Processes
        taskQueue  = multiprocessing.Queue()
        endQueue   = multiprocessing.Queue()
        workerList = []
        for i in range(self.processNum):
            workerList.append(multiprocessing.Process(target = ImageDownloaderRunner, args = (taskQueue, endQueue, )))
            workerList[i].start()

        for episode in self.episodeLists:
            if os.path.exists(os.path.join(os.path.realpath("Download"), self.manga, episode["episodeName"])):
                self.logger.info("AlreadyExistsEpisode, Skip ( EpisodeName : %s )" % (episode["episodeName"]))
                continue
            print("EpisodeName : %s, URL : %s" % (episode["episodeName"], episode["url"]))
            imageList = self.GetImageLists(episode["episodeName"], episode["url"])
            if imageList == False:
                self.logger.info("Can't download episode ( EpisodeName : %s, URL : %s )" % (episode["episodeName"], episode["url"]))
                continue
            for imageData in imageList:
                taskQueue.put(imageData)

        # Process End Checking
        while True:
            time.sleep(1)
            if endQueue.qsize() >= self.processNum:
                break

        # Kill all workers
        for worker in workerList:
            worker.terminate()

        self.logger.info("Download Completed")
        return True

    def UpdateManga(self):
        self.logger.info("Update Started")
        if not os.path.exists(os.path.realpath("Download")):
            self.logger.info("DirectoryNotExists ( Dir : %s )" % (os.path.exists(os.path.realpath("Download"))))
            return True

        for subPath, subDirs, subFiles in os.walk(os.path.realpath("Download")):
            for subDir in subDirs:
                mangaNumber = int(subDir.split("]")[0][1:])
                self.Run(mangaNumber = mangaNumber)
            break
            # for 1 depth

        self.logger.info("Update Ended")

    def GetImageLists(self, episodeName, targetURL):
        imageList = []

        # Try 5 times
        caps = DesiredCapabilities.PHANTOMJS
        caps["phantomjs.page.settings.userAgent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36"
        driver = webdriver.PhantomJS(self.driverPath, desired_capabilities=caps)
        driver.set_page_load_timeout(60)  # 60 seconds timeout
        for i in range(5):
            try:
                driver.get(targetURL)
            except Exception as e:
                self.logger.error("EpisodeLoadError ( episodeName : %s, url : %s ). Retry..." % (episodeName, targetURL))
                if i == 4:
                    # Exception Occured 5 times
                    return False
                continue
            else:
                self.logger.debug("Episode Load Success ( episodeName : %s, url : %s )" % (episodeName, targetURL))
                break

        if "Error 404" in driver.title:
            self.logger.error("EpisodeLoadError 404 ( episodeName : %s, url : %s )." % (episodeName, targetURL))
            return False

        source = BeautifulSoup(driver.page_source, "html5lib")
        currentURL = driver.current_url
        driver.quit()

        # Images with a Tag
        aTagList = source.find_all('a',
            {
                "href": lambda L: L and (L.startswith('http://www.yuncomics.com/wp-content') or L.startswith('http://wasabisyrup.com/storage/gallery/') or
                ".jpg" in L.lower() or ".png" in L.lower() or ".jpeg" in L.lower() or ".gif" in L.lower() or ".bmp" in L.lower())
             }
        )
        for aTagNum in range(len(aTagList)):
            imageList.append({"url":aTagList[aTagNum]['href']})

        # Images without a Tag
        if len(aTagList) == 0:
            imgTagList = source.find_all('img')
            for imgTagNum in range(len(imgTagList)):
                # Data-src check
                if imgTagList[imgTagNum].has_attr('data-src'):
                    tmpURL = imgTagList[imgTagNum]['data-src']
                else:
                    tmpURL = imgTagList[imgTagNum]['src']

                # '?' Check
                if "?" in tmpURL:
                    tmpURL = tmpURL.split("?")[0]

                if "yuncomics" in tmpURL:
                    imageList.append({"url":tmpURL})
                elif ("wasabisyrup" in targetURL or "wasabisyrup" in currentURL)  and (".jpg" in tmpURL.lower() or ".png" in tmpURL.lower() or ".jpeg" in tmpURL.lower() or ".gif" in tmpURL.lower() or ".bmp" in tmpURL.lower()):
                    imageList.append({"url":"http://wasabisyrup.com" + tmpURL})

        imageList = RemoveDuplicate(imageList)
        for imageNum in range(len(imageList)):
            imageList[imageNum]["savePath"] = os.path.join(os.path.realpath("Download"), self.manga, episodeName, "%03d.jpg" % (imageNum + 1))
            imageList[imageNum]["url"] = imageList[imageNum]["url"][:7] + quote(imageList[imageNum]["url"][7:])

        return imageList

    def GetEpisodeLists(self, source):
        episodeList = []
        aTagList = source.findAll('a')
        for i in aTagList:
            try:
                if 'http://www.yuncomics.com/archives' in i['href'] or 'http://www.shencomics.com/archives' in i['href'] or 'http://blog.yuncomics.com/archives' in i['href'] or 'http://wasabisyrup.com/archives' in i['href']:
                    episodeName = ValidateFileName(i.text.strip())
                    if episodeName == "":  # Duplicate
                        continue
                    episodeList.append({"episodeName":episodeName, "url":i['href']})
            except:  # 'a' tag without 'href'
                continue
        return episodeList

    def Crawl(self, targetURL):
        """ Crawling Only One URL's HTML """
        # Try 3 times
        for i in range(3):
            try:
                html = self.opener.open(targetURL).read()
            except:
                self.logger.error("CrawlError ( url : %s )" % (targetURL))
                continue
            else:
                return html
        return False

if __name__ == "__main__":
    multiprocessing.freeze_support()
    crawler = MaruCrawler(processNum = 4)
    crawler.PrintBanner()
    print("  <<< Select Menu >>>  ")
    print(" 1. Download Manga")
    print(" 2. Update Manga")
    while True:
        try:
            select = int(input("=> "))
            if select == 1 or select == 2:
                break
        except:
            print(" Please input 1 or 2")

    if select == 1:
        try:
            mangaNumber = int(input(" Input Manga ID : "))
        except:
            print(" Please input only integer")
        else:
            crawler.Run(mangaNumber)
    elif select == 2:
        crawler.UpdateManga()