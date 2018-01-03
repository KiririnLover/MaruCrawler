import time
import multiprocessing
import multiprocessing.queues
import urllib.request

from Utils import *

class ImageDownloader():
    def __init__(self):
        self.logger = CreateLogger("ImageDownloader")
        self.opener = urllib.request.build_opener()
        self.opener.addheaders = [('Accept','text/html, application/xhtml+xml, image/jxr, */*'), ('Accept-Language', 'ko,ja;q=0.5'), ('User-Agent', "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.84 Safari/537.36"), ('Accept-Encoding', 'gzip, deflate')]

    def DownloadImage(self, targetURL, savePath):
        for i in range(3):
            try:
                self.logger.debug("DownloadImage Started ( url : %s, savePath : %s ) " % (targetURL, savePath))
                source = self.opener.open(targetURL, timeout=10).read()
            except Exception as e:
                self.logger.error("DownloadImageError ( url : %s, savePath : %s, why : %s )" % (targetURL, savePath, str(e)))
                continue
            else:
                Mkdirs(savePath)
                with open(savePath, "bw+") as f:
                    f.write(source)
                return True
        return False

def ImageDownloaderRunner(taskQueue, endQueue):
    downloader = ImageDownloader()
    endQueue.put(1)
    while True:
        task = taskQueue.get()
        endQueue.get()
        downloader.DownloadImage(task["url"], task["savePath"])
        endQueue.put(1)