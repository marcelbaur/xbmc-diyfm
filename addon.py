# -*- coding: utf-8 -*-

import urllib, urllib2, re, sys, os, json
import xml.etree.ElementTree as ET
from datetime import datetime
import xbmcplugin, xbmcgui, xbmc, xbmcaddon


PROJECT_ROOT, tail = os.path.abspath(__file__).split('addon.py')
DATA_DIR = os.path.join(PROJECT_ROOT, 'resources', 'data')
RADIO_FILE_PATH = os.path.join(DATA_DIR, 'groupRadioStations.xml')
__settings__ = xbmcaddon.Addon(id='plugin.audio.diyfm')
API_KEY = __settings__.getSetting('api_key')
API_URL = "http://diy.fm/rest/v1/media/podcasts.xml?apiKey=%s" % (API_KEY)
API_USER_URL = "https://diy.fm/rest/v1/user/token.xml?apiKey=%s" % (API_KEY)
API_PERS_RADIO_URL = 'http://diy.fm/rest/v1/setting/overview.xml?apiKey=%s&userToken=%s'
DATE_FORMAT = '%d-%m-%Y'


def parameters_string_to_dict(parameters):
    paramDict = {}
    if parameters:
        paramPairs = parameters[1:].split("&")
        for paramsPair in paramPairs:
            paramSplits = paramsPair.split('=')
            if (len(paramSplits)) == 2:
                paramDict[paramSplits[0]] = paramSplits[1]
    return paramDict


def load_station_groups():
    file = ET.parse(RADIO_FILE_PATH)
    root = file.getroot()
    return [child for child in root]


def load_stations(url):
    file = ET.parse(RADIO_FILE_PATH)
    root = file.getroot()
    radio_stations = root.find('.')
    stations = []
    for group in radio_stations:
        if group.attrib['name'] == url:
            stations = [station for station in group]
            break
    return stations


def load_station(station_id):
    file = ET.parse(RADIO_FILE_PATH)
    root = file.getroot()
    for station in root.findall('./group/station'):
        if station.find('id').text == station_id:
            return station


def load_podcast_xml():
    request = urllib2.Request(API_URL)
    try:
        response = urllib2.urlopen(request)
    except urllib2.URLError as e:
        response = None
    if response:
        file_name = '%s.xml' % (datetime.now().strftime(DATE_FORMAT))
        file = open(os.path.join(DATA_DIR, file_name), 'wb')
        file.write(response.read())
        file.close()


def get_genres():
    podcast_file = '%s.xml' % (datetime.now().strftime(DATE_FORMAT))
    file = open(os.path.join(DATA_DIR, podcast_file), 'r')
    xml = ET.fromstring(file.read())
    file.close()
    all_genres = xml.findall('./podcasts/podcast/genre')
    ge = {}
    grouped_genres = {'En': [], 'De': [], 'Fr': [], 'It': [], 'Rm': []}
    for genre in all_genres:
        if not genre.find('id').text in ge:
            ge[genre.find('id').text] = genre

    for g_id, genre in ge.items():
        for lang in genre:
            if lang.tag != 'id':
                grouped_genres[lang.tag[-2:]].append({'id': g_id, 'title': unicode(lang.text)})

    for key in grouped_genres.keys():
        grouped_genres[key] = sorted(grouped_genres[key], key=lambda k: k['title'])

    with open(os.path.join(DATA_DIR, 'genres.json'), 'w') as outfile:
        json.dump(grouped_genres, outfile)


def diyfmLogin():
    post_data = {}
    post_data['user'] = __settings__.getSetting('diyfm_username')
    post_data['password'] = __settings__.getSetting('diyfm_pass')
    request = urllib2.Request(API_USER_URL, urllib.urlencode(post_data))
    request.get_method = lambda: 'POST'
    try:
        response = urllib2.urlopen(request)
    except urllib2.HTTPError as e:
        if e.code == 401:
            xbmc.executebuiltin('Notification(%s, %s, %d)' % (__settings__.getAddonInfo('name'),
                                                          'Please specify correct username and password', 5000))
        response = None
    if response:
        xml_resp = ET.fromstring(response.read())
        if xml_resp.find('./status/statusCode').text == '200':
            __settings__.setSetting('access_token', xml_resp.find('userToken').text)
        else:
            xbmc.executebuiltin('Notification(%s, %s, %d)' % (__settings__.getAddonInfo('name'),
                                                          'Please specify correct username and password', 5000))


def get_personalize_stream():
    request = urllib2.Request(API_PERS_RADIO_URL % (API_KEY, __settings__.getSetting('access_token')))
    try:
        xml_response = ET.fromstring(urllib2.urlopen(request).read())
    except urllib2.HTTPError as e:
        # token expire
        if e.code == 423:
            # get new user token
            diyfmLogin()
            # update userToken in request object
            request = urllib2.Request(API_PERS_RADIO_URL % (API_KEY, __settings__.getSetting('access_token')))
            xml_response = ET.fromstring(urllib2.urlopen(request).read())
    return xml_response or None


def index():
    for radio in load_station_groups():
        addDir(radio.attrib['title'], radio.attrib['name'], 'radioStream')
    addDir('Podcast', 'podcast', 'podcastIndex')
    if __settings__.getSetting('diyfm_username') == '' or __settings__.getSetting('diyfm_pass') == '':
        xbmc.executebuiltin('Notification(%s, %s, %d)' % (__settings__.getAddonInfo('name'),
                                                          'You can indicate your login and password for diy.fm in the plugin settings', 10000))
    else:
        if __settings__.getSetting('access_token') == '':
            diyfmLogin()
        xml_response = get_personalize_stream()
        if not xml_response is None:
            for elem in xml_response.find('./settings'):
                if elem.find('isDefaultMedia').text == 'true':
                    __settings__.setSetting('default_stream', elem.find('./medium/name').text)
                    __settings__.setSetting('def_stream_id', elem.find('./medium/id').text)
                    if elem.find('hasNewsOnFullHour').text == 'true':
                        __settings__.setSetting('news_stream', elem.find('./newsMedium/name').text)
                        __settings__.setSetting('news_stream_id', elem.find('./newsMedium/id').text)
                    break
        if __settings__.getSetting('def_stream_id'):
            station = load_station(__settings__.getSetting('def_stream_id'))
            xbmc.Player().play(station.find('streamUrl').text)


def radioStreams(url):
    for station in load_stations(url):
        addItem(station.find('name').text, station.find('streamUrl').text, station.find('imgUrl').text)


def podcastIndex():
    file_name = '%s.xml' % (datetime.now().strftime(DATE_FORMAT))
    pattern = re.compile(r'^[0-9]{2}-[0-9]{2}-[0-9]{4}.xml$')
    is_exist = False
    for file in os.listdir(DATA_DIR):
        if pattern.match(file) and file != file_name:
            os.remove(os.path.join(DATA_DIR, file))
        elif file == file_name:
            is_exist = True
    if not is_exist:
        load_podcast_xml()
        get_genres()
    genres_file = os.path.join(DATA_DIR, 'genres.json')
    file = open(genres_file, 'r')
    json_genres = json.load(file)
    file.close()
    language = xbmc.getLanguage()
    if language == 'German':
        localize_genres = json_genres.get('De')
    elif language[:2] in json_genres:
        localize_genres = json_genres.get(language[:2])
    else:
        localize_genres = json_genres.get('En')

    for genre in localize_genres:
        addDir(genre.get('title'), genre.get('id'), 'podcastGenre')


def podcastGenreItems(genre_id):
    podcast_file = '%s.xml' % (datetime.now().strftime(DATE_FORMAT))
    file = open(os.path.join(DATA_DIR, podcast_file), 'r')
    podcast_xml = ET.parse(file)
    root = podcast_xml.getroot()
    for podcast in root.find('podcasts'):
        if podcast.find('genre').find('id').text == genre_id:
            addDir(podcast.find('name').text, podcast.find('feedUrl').text, 'podcastItem', podcast.find('imgUrl').text)


def podcastItems(url):
    resp = getUrl(url)
    xml = ET.fromstring(resp)
    for item in xml.findall('./channel/item'):
        if check_url(item.find('enclosure').attrib['url']):
            addItem(item.find('title').text, item.find('enclosure').attrib['url'], '')


def getUrl(url):
        req = urllib2.Request(urllib.unquote_plus(url))
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 6.1; rv:11.0) Gecko/20100101 Firefox/11.0')
        try:
            response = urllib2.urlopen(req, timeout=30)
        except urllib2.URLError:
            response = None
        if response:
            data = response.read()
            response.close()
        else:
            data = None
        return data


def check_url(url):
    request = urllib2.Request(url)
    request.get_method = lambda: 'HEAD'
    try:
        response = urllib2.urlopen(request)
    except urllib2.HTTPError as e:
        response = None
    return not response is None


def addItem(name, url, iconimage, podcast_feed=''):
    item = xbmcgui.ListItem(name, iconImage=iconimage if iconimage else '',
                            thumbnailImage=iconimage if iconimage else '')
    item.setInfo(type='Music', infoLabels={'Title': name})
    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=item)


def addDir(name, url, mode, dir_img=''):
    u = sys.argv[0] + "?url=" + urllib.quote_plus(url) + "&mode=" + str(mode)
    ok = True
    liz = xbmcgui.ListItem(name, iconImage=dir_img if dir_img else '', thumbnailImage='')
    liz.setInfo(type="Music", infoLabels={"Title": name})
    ok = xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=u, listitem=liz, isFolder=True)
    return ok


params = parameters_string_to_dict(sys.argv[2])
mode = None

mode = params.get('mode')
url = params.get('url')

if mode is None:
    index()
elif mode == 'radioStream':
    radioStreams(url)
elif mode == 'podcastIndex':
    podcastIndex()
elif mode == 'podcastGenre':
    podcastGenreItems(url)
elif mode == 'podcastItem':
    podcastItems(url)

xbmcplugin.endOfDirectory(int(sys.argv[1]))
