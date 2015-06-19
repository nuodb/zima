#!/usr/bin/env nuopython
import urllib2, json, sys, time
from bs4 import BeautifulSoup

URL = "http://tools/bamboo/rest/api/latest/result/{}.json?expand=artifacts" 

class NoSuchBuildException(Exception):
    pass

def match(link):
    return ("tar" in link or "Linux-dist" in link) and \
        "Mac" not in link and \
        "olaris" not in link and \
        "-tools-" not in link and \
        "OSX" not in link

def get_metadata(build):
    try:
        return urllib2.urlopen(URL.format(build))
    except urllib2.HTTPError:
        raise NoSuchBuildException("No such build {} (404)".format(build))

def scan(url):
    try:
        listing = urllib2.urlopen(url)
    except:
        return None
    soup = BeautifulSoup(listing.read())
    links = soup.find_all('a')
    for link in links:
        href = link.get('href')
        if href[-6:] == "tar.gz" and match(href):
            if href[0:4] == "http":
                return href
            return "http://tools/"+href

class HeadRequest(urllib2.Request):
    def get_method(self):
        return "HEAD"

def scan2(url):
    try:
        resp = urllib2.urlopen(HeadRequest(url))
    except:
        return False
    head = resp.info()
    return head.get("Content-Type")[0:4] != "text"

class Break(Exception):
    pass

def get_link(build):
    found = False
    link = None
    retries = 5

    try:
        while True:
            obj = json.loads(get_metadata(build).read())
            try:
                for item in obj["artifacts"]["artifact"]:
                    try:
                        link = item["link"]["href"]
                    except:
                        continue
                    if match(link):
                        if link[-1] == '/':
                            candidate = scan(link)
                            if scan2(candidate):
                                msg = candidate
                                found = True
                                raise Break()
                        else:
                            msg = link
                            found = True
                            raise Break()
                retries = retries - 1
                time.sleep(30)
                if retries < 0:
                    raise Break()
            except KeyError:
                retries = retries - 1
                time.sleep(30)
                if retries < 0:
                    raise Break()
    except Break:
        pass        

    if link and not found:
        url = link[0:link.find("shared")]+"JOB1/"  ## use the last value of link from above
        candidate = scan(url)
        if scan2(candidate):
            msg = candidate
            found = True
        else:
            candidate2 = scan(candidate)
            if scan2(candidate2):
                msg = candidate2
                found = True

    if found:
        return msg
    else:
        return None

def get_build():
    try:
        return sys.argv[1]
    except IndexError:
        print "No build supplied"
        exit(1)
    
if __name__ == "__main__":
    build = get_build()
    lnk = get_link(build)
    if lnk:
        print lnk
    else:
        print "No artifacts found for {}".format(build)
        exit(1)
