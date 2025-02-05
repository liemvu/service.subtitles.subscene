# -*- coding: utf-8 -*-

import os
import sys
import xbmc
import urllib
import urllib2
import xbmcvfs
import xbmcaddon
import xbmcgui
import xbmcplugin
import uuid
import unicodedata
import re
import string
import difflib
import HTMLParser
from operator import itemgetter


ADD_ON = xbmcaddon.Addon()
AUTHOR = ADD_ON.getAddonInfo('author')
SCRIPT_ID = ADD_ON.getAddonInfo('id')
SCRIPT_NAME = ADD_ON.getAddonInfo('name').encode('utf-8')
VERSION = ADD_ON.getAddonInfo('version')

CWD = unicode(xbmc.translatePath(ADD_ON.getAddonInfo('path')), 'utf-8')
PROFILE = unicode(xbmc.translatePath(ADD_ON.getAddonInfo('profile')), 'utf-8')
RESOURCE = unicode(xbmc.translatePath(os.path.join(CWD, 'resources', 'lib')), 'utf-8')
TEMP = unicode(xbmc.translatePath(os.path.join(PROFILE, 'temp', '')), 'utf-8')

sys.path.append(RESOURCE)

from SubsceneUtilities import log, geturl, get_language_codes, subscene_languages, get_episode_pattern
from ordinal import ordinal

main_url = "https://subscene.com"

aliases = {
    "marvels agents of shield" : "Agents of Shield",
    "marvels agents of s.h.i.e.l.d" : "Agents of Shield",
    "marvels jessica jones": "Jessica Jones",
    "dcs legends of tomorrow": "Legends of Tomorrow"
}

search_section_pattern = "<h2 class=\"(?P<section>\w+)\">(?:[^<]+)</h2>\s+<ul>(?P<content>.*?)</ul>"
movie_season_pattern = ("<a href=\"(?P<link>/subtitles/[^\"]*)\">(?P<title>[^<]+)\((?P<year>\d{4})\)</a>\s+"
                        "</div>\s+<div class=\"subtle count\">\s+(?P<numsubtitles>\d+)")


def _xmbc_localized_string_utf8(string_id):
    return ADD_ON.getLocalizedString(string_id).encode('utf-8')


def _xbmc_notification(string_id, heading=SCRIPT_NAME):
    message = _xmbc_localized_string_utf8(string_id)
    xbmcgui.Dialog().notification(heading, message)


def seasons(i):
    """Seasons as strings for searching"""
    i = int(i)
    if i == 0:
        return 'Specials'
    else:
        return ordinal(i)


def rmtree(path):
    if isinstance(path, unicode):
        path = path.encode('utf-8')
    dirs, files = xbmcvfs.listdir(path)
    for dir in dirs:
        rmtree(os.path.join(path, dir))
    for file in files:
        xbmcvfs.delete(os.path.join(path, file))
    xbmcvfs.rmdir(path)


try:
    rmtree(TEMP)
except:
    pass
xbmcvfs.mkdirs(TEMP)


def find_movie(content, title, year):
    found_urls = {}
    found_movies = []

    h = HTMLParser.HTMLParser()
    for secmatches in re.finditer(search_section_pattern, content, re.IGNORECASE | re.DOTALL):
        log(__name__, secmatches.group('section'))
        for matches in re.finditer(movie_season_pattern, secmatches.group('content'), re.IGNORECASE | re.DOTALL):
            if matches.group('link') in found_urls:
                if secmatches.group('section') == 'close':
                    found_movies[found_urls[matches.group('link')]]['is_close'] = True
                if secmatches.group('section') == 'exact':
                    found_movies[found_urls[matches.group('link')]]['is_exact'] = True
                continue
            found_urls[matches.group('link')] = len(found_movies)

            found_title = matches.group('title')
            found_title = h.unescape(found_title)
            log(__name__, "Found movie on search page: %s (%s)" % (found_title, matches.group('year')))
            found_movies.append(
                {'t': string.lower(found_title),
                 'y': int(matches.group('year')),
                 'is_exact': secmatches.group('section') == 'exact',
                 'is_close': secmatches.group('section') == 'close',
                 'l': matches.group('link'),
                 'c': int(matches.group('numsubtitles'))})

    year = int(year)
    title = string.lower(title)
    # Priority 1: matching title and year
    if year > -1:
        for movie in found_movies:
            if string.find(movie['t'], title) > -1:
                if movie['y'] == year:
                    log(__name__, "Matching movie found on search page: %s (%s)" % (movie['t'], movie['y']))
                    return movie['l']

    # Priority 2: matching title and one off year
    if year > -1:
        for movie in found_movies:
            if string.find(movie['t'], title) > -1:
                if movie['y'] == year + 1 or movie['y'] == year - 1:
                    log(__name__, "Matching movie found on search page (one off year): %s (%s)" % (movie['t'], movie['y']))
                    return movie['l']

    # Priority 3: "Exact" match according to search result page
    close_movies = []
    for movie in found_movies:
        if movie['is_exact']:
            log(__name__, "Using 'Exact' match: %s (%s)" % (movie['t'], movie['y']))
            return movie['l']
        if movie['is_close']:
            close_movies.append(movie)

    # Priority 4: "Close" match according to search result page
    if len(close_movies) > 0:
        close_movies = sorted(close_movies, key=itemgetter('c'), reverse=True)
        log(__name__, "Using 'Close' match: %s (%s)" % (close_movies[0]['t'], close_movies[0]['y']))
        return close_movies[0]['l']

    return None


def find_movie_google_edition(content, title, year):
    found_urls = []
    found_movies = []
    # match https://subscene.com/subtitles/13-going-on-30
    # n not https://subscene.com/subtitles/13-going-on-30/english/516887
    search_result_url_pattern = "(?P<url>https:\/\/subscene\.com\/subtitles\/.+?)[\"/&<?]"

    h = HTMLParser.HTMLParser()
    for matches in re.finditer(search_result_url_pattern, content, re.IGNORECASE):
        found_url = matches.group('url')
        log(__name__, "Found match: " + found_url)
        if found_url in found_urls:
            continue
            
        found_urls.append(found_url)
        
        return found_url

        #found_title = matches.group('title')
        #found_title = h.unescape(found_title)
        #log(__name__, "Found movie on search page: %s (%s)" % (found_title, matches.group('year')))
        #found_movies.append(
        #    {'t': string.lower(found_title),
        #     'y': int(matches.group('year')),
        #     'is_exact': secmatches.group('section') == 'exact',
        #     'is_close': secmatches.group('section') == 'close',
        #     'l': matches.group('link'),
        #     'c': int(matches.group('numsubtitles'))})

    #year = int(year)
    #title = string.lower(title)
    # Priority 1: matching title and year
    #if year > -1:
    #    for movie in found_movies:
    #        if string.find(movie['t'], title) > -1:
    #            if movie['y'] == year:
    #                log(__name__, "Matching movie found on search page: %s (%s)" % (movie['t'], movie['y']))
    #                return movie['l']

    # Priority 2: matching title and one off year
    #if year > -1:
    #    for movie in found_movies:
    #        if string.find(movie['t'], title) > -1:
    #            if movie['y'] == year + 1 or movie['y'] == year - 1:
    #                log(__name__, "Matching movie found on search page (one off year): %s (%s)" % (movie['t'], movie['y']))
    #                return movie['l']

    # Priority 3: "Exact" match according to search result page
    #close_movies = []
    #for movie in found_movies:
    #    if movie['is_exact']:
    #        log(__name__, "Using 'Exact' match: %s (%s)" % (movie['t'], movie['y']))
    #        return movie['l']
    #    if movie['is_close']:
    #        close_movies.append(movie)

    # Priority 4: "Close" match according to search result page
    #if len(close_movies) > 0:
    #    close_movies = sorted(close_movies, key=itemgetter('c'), reverse=True)
    #    log(__name__, "Using 'Close' match: %s (%s)" % (close_movies[0]['t'], close_movies[0]['y']))
    #    return close_movies[0]['l']

    return None


def find_tv_show_season(content, tvshow, season):
    url_found = None
    found_urls = []
    possible_matches = []
    all_tvshows = []

    h = HTMLParser.HTMLParser()
    for matches in re.finditer(movie_season_pattern, content, re.IGNORECASE | re.DOTALL):
        found_title = matches.group('title')
        found_title = h.unescape(found_title)

        if matches.group('link') in found_urls:
            continue
        log(__name__, "Found tv show season on search page: %s" % found_title)
        found_urls.append(matches.group('link'))
        s = difflib.SequenceMatcher(None, string.lower(found_title + ' ' + matches.group('year')), string.lower(tvshow))
        all_tvshows.append(matches.groups() + (s.ratio() * int(matches.group('numsubtitles')),))
        # try to find match on title
        if string.find(string.lower(found_title), string.lower(tvshow)) > -1:
            # try to match season
            if string.find(string.lower(found_title), string.lower(season)) > -1:
                log(__name__, "Matching tv show season found on search page: %s" % found_title)
                possible_matches.append(matches.groups())
            # try to match with season if first season (ie one season only series)
            elif string.lower(season) == "first" and string.find(string.lower(found_title), "season") == -1:
                log(__name__, "Matching tv show (no season) found on search page: %s" % found_title)
                possible_matches.append(matches.groups())

    if len(possible_matches) > 0:
        possible_matches = sorted(possible_matches, key=lambda x: -int(x[3]))
        url_found = possible_matches[0][0]
        log(__name__, "Selecting matching tv show with most subtitles: %s (%s)" % (
            possible_matches[0][1], possible_matches[0][3]))
    else:
        if len(all_tvshows) > 0:
            all_tvshows = sorted(all_tvshows, key=lambda x: -int(x[4]))
            url_found = all_tvshows[0][0]
            log(__name__, "Selecting tv show with highest fuzzy string score: %s (score: %s subtitles: %s)" % (
                all_tvshows[0][1], all_tvshows[0][4], all_tvshows[0][3]))

    return url_found


def find_tv_show_season_google_edition(content, tvshow, season, year):
    url_found = None
    found_urls = []
    possible_matches = []
    all_tvshows = []
    search_result_url_pattern = "(?P<url>https:\/\/subscene\.com\/subtitles\/.+?)[\"/&<?]"
    tvshow_slug = string.lower(tvshow).replace(" ", "-")

    h = HTMLParser.HTMLParser()
    for matches in re.finditer(search_result_url_pattern, content, re.IGNORECASE):
        found_url = matches.group('url')

        if found_url in found_urls:
            continue
        log(__name__, "Found match on search page: %s" % found_url)
        found_slug = string.lower(found_url.split("/")[-1])
        found_urls.append(found_url)
        score = difflib.SequenceMatcher(None, found_slug, tvshow_slug).ratio() + difflib.SequenceMatcher(None, found_slug, tvshow_slug + "-" + year).ratio()
        all_tvshows.append([score, found_url])
        # try to find match on title
        log(__name__, "Trying to match on title: (%s) and (%s)" % (found_slug, tvshow_slug))
        if string.find(found_slug, tvshow_slug) > -1:
            # try to match season
            if string.find(string.lower(found_slug), string.lower(season)) > -1:
                log(__name__, "Matching tv show season found on search page: %s" % found_url)
                possible_matches.append([score, found_url])
            # try to match with season if first season (ie one season only series)
            elif string.lower(season) == "first" and string.find(string.lower(found_url), "season") == -1:
                log(__name__, "Matching tv show (no season) found on search page: %s" % found_url)
                possible_matches.append([score, found_url])

    if len(possible_matches) > 0:
        possible_matches = sorted(possible_matches, key=lambda x: -int(x[0]))
        url_found = possible_matches[0][1]
        log(__name__, "Selecting matching tv show with highest fuzzy string score: %s (%s)" % (
            possible_matches[0][0], possible_matches[0][1]))
    else:
        if len(all_tvshows) > 0:
            all_tvshows = sorted(all_tvshows, key=lambda x: -int(x[0]))
            url_found = all_tvshows[0][1]
            log(__name__, "Selecting possible tv show with highest fuzzy string score: %s (score: %s)" % (
                all_tvshows[0][0], all_tvshows[0][1]))

    return url_found


def append_subtitle(item):
    title = item['filename']
    if 'comment' in item and item['comment'] != '':
        title = "%s [COLOR gray][I](%s)[/I][/COLOR]" % (title, item['comment'])
    listitem = xbmcgui.ListItem(label=item['lang']['name'],
                                label2=title,
                                iconImage=item['rating'],
                                thumbnailImage=item['lang']['2let'])

    listitem.setProperty("sync", 'true' if item["sync"] else 'false')
    listitem.setProperty("hearing_imp", 'true' if item["hearing_imp"] else 'false')

    # below arguments are optional, it can be used to pass any info needed in download function
    # anything after "action=download&" will be sent to addon once user clicks listed subtitle to downlaod
    url = "plugin://%s/?action=download&link=%s&filename=%s" % (SCRIPT_ID,
                                                                item['link'],
                                                                item['filename'])
    if 'episode' in item:
        url += "&episode=%s" % item['episode']
    # add it to list, this can be done as many times as needed for all subtitles found
    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=listitem, isFolder=False)


def getallsubs(url, allowed_languages, filename="", episode=""):
    subtitle_pattern = ("<td class=\"a1\">\s+<a href=\"(?P<link>/subtitles/[^\"]+)\">\s+"
                        "<span class=\"[^\"]+ (?P<quality>\w+-icon)\">\s+(?P<language>[^\r\n\t]+)\s+</span>\s+"
                        "<span>\s+(?P<filename>[^\r\n\t]+)\s+</span>\s+"
                        "</a>\s+</td>\s+"
                        "<td class=\"[^\"]+\">\s+(?P<numfiles>[^\r\n\t]*)\s+</td>\s+"
                        "<td class=\"(?P<hiclass>[^\"]+)\">"
                        "(?:.*?)<td class=\"a6\">\s+<div>\s+(?P<comment>[^\"]+)&nbsp;\s*</div>")

    codes = get_language_codes(allowed_languages)
    if len(codes) < 1:
        _xbmc_notification(32004)
        return
    log(__name__, 'LanguageFilter='+','.join(codes))
    #content, response_url = geturl(url, 'LanguageFilter='+','.join(codes))
    content, response_url = geturl(url)

    if content is None:
        log(__name__, 'response empty')
        return

    subtitles = []
    h = HTMLParser.HTMLParser()
    episode_regex = None
    any_episode_regex = None
    if episode != "":
        episode_regex = re.compile(get_episode_pattern(episode), re.IGNORECASE)
        any_episode_regex = re.compile("(?:s[0-9]{2}e[0-9]{2}|\D[0-9]{1,2}x[0-9]{2})", re.IGNORECASE)
        log(__name__, "regex: %s" % get_episode_pattern(episode))

    for matches in re.finditer(subtitle_pattern, content, re.IGNORECASE | re.DOTALL):
        log(__name__, "Found subtitle: %s" % matches.groupdict())
        numfiles = -1
        if matches.group('numfiles') != "":
            numfiles = int(matches.group('numfiles'))
        languagefound = matches.group('language')
        language_info = None
        if languagefound in subscene_languages:
            language_info = subscene_languages[languagefound]
        else:
            log(__name__, "not in subscene_languages: %s" % languagefound)
            continue

        log(__name__, "language_info: %s, language_info['3let']: %s, allowed_languages: %s" % (language_info, language_info['3let'], allowed_languages))
        if language_info is not None and language_info['3let'] in allowed_languages:
            link = main_url + matches.group('link')
            subtitle_name = string.strip(matches.group('filename'))
            hearing_imp = (matches.group('hiclass') == "a41")
            rating = '0'
            if matches.group('quality') == "bad-icon":
                continue
            if matches.group('quality') == "positive-icon":
                rating = '5'

            comment = re.sub("[\r\n\t]+", " ", h.unescape(string.strip(matches.group('comment'))))

            sync = False
            if filename != "" and string.lower(filename) == string.lower(subtitle_name):
                sync = True

            if episode != "":
                # log(__name__, "match: "+subtitle_name)
                # matching episode
                if episode_regex.search(subtitle_name):
                    subtitles.append({'rating': rating, 'filename': subtitle_name, 'sync': sync, 'link': link,
                                      'lang': language_info, 'hearing_imp': hearing_imp, 'comment': comment})
                # multiple files
                elif numfiles > 2:
                    subtitle_name = subtitle_name + ' ' + (_xmbc_localized_string_utf8(32001) % int(matches.group('numfiles')))
                    subtitles.append({'rating': rating, 'filename': subtitle_name, 'sync': sync, 'link': link,
                                      'lang': language_info, 'hearing_imp': hearing_imp, 'comment': comment,
                                      'episode': episode})
                # not matching any episode (?)
                elif not any_episode_regex.search(subtitle_name):
                    subtitles.append({'rating': rating, 'filename': subtitle_name, 'sync': sync, 'link': link,
                                      'lang': language_info, 'hearing_imp': hearing_imp, 'comment': comment,
                                      'episode': episode})
            else:
                subtitles.append({'rating': rating, 'filename': subtitle_name, 'sync': sync, 'link': link,
                                  'lang': language_info, 'hearing_imp': hearing_imp, 'comment': comment})

    subtitles.sort(key=lambda x: [not x['sync'], not x['lang']['name'] == PreferredSub])
    log(__name__, "subtitles count: %s" % len(subtitles))
    for s in subtitles:
        append_subtitle(s)


def prepare_search_string(s):
    s = string.strip(s)
    s = re.sub(r'\s+\(\d\d\d\d\)$', '', s)  # remove year from title
    return s


def search_movie(title, year, languages, filename):
    search_movie_google_edition(title, year, languages, filename)
    return
    
    title = prepare_search_string(title)

    log(__name__, "Search movie = %s" % title)
    url = main_url + "/subtitles/titlesearch?q=" + urllib.quote_plus(title)
    content, response_url = geturl(url)

    if content is not None:
        log(__name__, "Multiple movies found, searching for the right one ...")
        subspage_url = find_movie(content, title, year)
        if subspage_url is not None:
            log(__name__, "Movie found in list, getting subs ...")
            url = main_url + subspage_url
            getallsubs(url, languages, filename)
        else:
            log(__name__, "Movie not found in list: %s" % title)
            if string.find(string.lower(title), "&") > -1:
                title = string.replace(title, "&", "and")
                log(__name__, "Trying searching with replacing '&' to 'and': %s" % title)
                subspage_url = find_movie(content, title, year)
                if subspage_url is not None:
                    log(__name__, "Movie found in list, getting subs ...")
                    url = main_url + subspage_url
                    getallsubs(url, languages, filename)
                else:
                    log(__name__, "Movie not found in list: %s" % title)


def search_movie_google_edition(title, year, languages, filename):
    title = prepare_search_string(title)

    log(__name__, "Search movie = %s" % title)
    url = "https://www.google.com/search?q=subscene.com+" + urllib.quote_plus(title)
    content, response_url = geturl(url)

    if content is not None:
        #log(__name__, "Multiple movies found, searching for the right one ...")
        subspage_url = find_movie_google_edition(content, title, year)
        if subspage_url is not None:
            log(__name__, "Movie found in list, getting subs ...")
            url = subspage_url
            getallsubs(url, languages, filename)
        else:
            log(__name__, "Movie not found in list: %s" % title)
            if string.find(string.lower(title), "&") > -1:
                title = string.replace(title, "&", "and")
                log(__name__, "Trying searching with replacing '&' to 'and': %s" % title)
                subspage_url = find_movie_google_edition(content, title, year)
                if subspage_url is not None:
                    log(__name__, "Movie found in list, getting subs ...")
                    url = subspage_url
                    getallsubs(url, languages, filename)
                else:
                    log(__name__, "Movie not found in list: %s" % title)


def search_tvshow(tvshow, season, episode, languages, filename, year):
    search_tvshow_google_edition(tvshow, season, episode, languages, filename, year)
    return
    
    tvshow = prepare_search_string(tvshow)
    season_ordinal = seasons(season)

    tvshow_lookup = tvshow.lower().replace("'", "").strip(".")
    if tvshow_lookup in aliases:
        log(__name__, 'found alias for "%s"' % tvshow_lookup)
        tvshow = aliases[tvshow_lookup]

    search_string = '{tvshow} - {season_ordinal} Season'.format(**locals())

    log(__name__, "Search tvshow = %s" % search_string)
    url = main_url + "/subtitles/titlesearch?q=" + urllib.quote_plus(search_string) + '&r=true'
    content, response_url = geturl(url)

    if content is not None:
        log(__name__, "Multiple tv show seasons found, searching for the right one ...")
        tv_show_seasonurl = find_tv_show_season(content, tvshow, season_ordinal)
        if tv_show_seasonurl is not None:
            log(__name__, "Tv show season found in list, getting subs ...")
            url = main_url + tv_show_seasonurl
            epstr = '{season}:{episode}'.format(**locals())
            getallsubs(url, languages, filename, epstr)


def search_tvshow_google_edition(tvshow, season, episode, languages, filename, year):
    tvshow = prepare_search_string(tvshow)
    season_ordinal = seasons(season)

    tvshow_lookup = tvshow.lower().replace("'", "").strip(".")
    if tvshow_lookup in aliases:
        log(__name__, 'found alias for "%s"' % tvshow_lookup)
        tvshow = aliases[tvshow_lookup]

    search_string = '{tvshow} - {season_ordinal} Season'.format(**locals())

    log(__name__, "Search tvshow = %s" % search_string)
    url = "https://www.google.com/search?q=subscene.com+" + urllib.quote_plus(search_string)
    content, response_url = geturl(url)

    if content is not None:
        #log(__name__, "Multiple tv show seasons found, searching for the right one ...")
        tv_show_seasonurl = find_tv_show_season_google_edition(content, tvshow, season_ordinal, year)
        if tv_show_seasonurl is not None:
            log(__name__, "Tv show season found in list, getting subs ...")
            url = tv_show_seasonurl
            epstr = '{season}:{episode}'.format(**locals())
            getallsubs(url, languages, filename, epstr)


def search_manual(searchstr, languages, filename):
    search_movie(searchstr, -1, languages, filename)


def search_filename(filename, languages):
    title, year = xbmc.getCleanMovieTitle(filename)
    log(__name__, "clean title: \"%s\" (%s)" % (title, year))
    try:
        yearval = int(year)
    except ValueError:
        yearval = 0
    match = re.search(r'\WS(?P<season>\d\d)E(?P<episode>\d\d)', filename, flags=re.IGNORECASE)
    if match is not None:
        tvshow = string.strip(title[:match.start('season') - 1])
        season = string.lstrip(match.group('season'), '0')
        episode = string.lstrip(match.group('episode'), '0')
        search_tvshow(tvshow, season, episode, languages, filename, yearval)
    elif title and yearval > 1900:
        search_movie(title, year, languages, filename)
    elif title:
        search_manual(title, languages, filename)
    else:
        search_manual(filename, languages, filename)


def search(item):
    filename = os.path.splitext(os.path.basename(item['file_original_path']))[0]
    log(__name__, "Search_subscene='%s', filename='%s', addon_version=%s" % (item, filename, VERSION))

    if item['mansearch']:
        search_manual(item['mansearchstr'], item['3let_language'], filename)
    elif item['tvshow'] and item['year']:
        search_tvshow(item['tvshow'], item['season'], item['episode'], item['3let_language'], filename, item['year'])
    elif item['title'] and item['year']:
        search_movie(item['title'], item['year'], item['3let_language'], filename)
    elif item['title']:
        search_filename(item['title'], item['3let_language'])
    else:
        search_filename(filename, item['3let_language'])


def download(link, episode=""):
    subtitle_list = []
    exts = [".srt", ".sub", ".txt", ".smi", ".ssa", ".ass"]
    downloadlink_pattern = "...<a href=\"(.+?)\" rel=\"nofollow\" onclick=\"DownloadSubtitle"

    uid = uuid.uuid4()
    tempdir = os.path.join(TEMP, unicode(uid))
    xbmcvfs.mkdirs(tempdir)

    content, response_url = geturl(link)
    match = re.compile(downloadlink_pattern).findall(content)
    if match:
        downloadlink = main_url + match[0]
        viewstate = 0
        previouspage = 0
        subtitleid = 0
        typeid = "zip"
        filmid = 0

        postparams = urllib.urlencode(
            {'__EVENTTARGET': 's$lc$bcr$downloadLink', '__EVENTARGUMENT': '', '__VIEWSTATE': viewstate,
             '__PREVIOUSPAGE': previouspage, 'subtitleId': subtitleid, 'typeId': typeid, 'filmId': filmid})

        useragent = ("User-Agent=Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.2.3) "
                       "Gecko/20100401 Firefox/3.6.3 ( .NET CLR 3.5.30729)")
        headers = {'User-Agent': useragent, 'Referer': link}
        log(__name__, "Fetching subtitles using url '%s' with referer header '%s' and post parameters '%s'" % (
            downloadlink, link, postparams))
        request = urllib2.Request(downloadlink, postparams, headers)
        response = urllib2.urlopen(request)

        if response.getcode() != 200:
            log(__name__, "Failed to download subtitle file")
            return subtitle_list

        local_tmp_file = os.path.join(tempdir, "subscene.xxx")
        packed = False

        try:
            log(__name__, "Saving subtitles to '%s'" % local_tmp_file)
            local_file_handle = xbmcvfs.File(local_tmp_file, "wb")
            local_file_handle.write(response.read())
            local_file_handle.close()

            # Check archive type (rar/zip/else) through the file header (rar=Rar!, zip=PK)
            myfile = xbmcvfs.File(local_tmp_file, "rb")
            myfile.seek(0,0)
            if myfile.read(1) == 'R':
                typeid = "rar"
                packed = True
                log(__name__, "Discovered RAR Archive")
            else:
                myfile.seek(0,0)
                if myfile.read(1) == 'P':
                    typeid = "zip"
                    packed = True
                    log(__name__, "Discovered ZIP Archive")
                else:
                    typeid = "srt"
                    packed = False
                    log(__name__, "Discovered a non-archive file")
            myfile.close()
            local_tmp_file = os.path.join(tempdir, "subscene." + typeid)
            xbmcvfs.rename(os.path.join(tempdir, "subscene.xxx"), local_tmp_file)
            log(__name__, "Saving to %s" % local_tmp_file)
        except:
            log(__name__, "Failed to save subtitle to %s" % local_tmp_file)

        if packed:
            xbmc.sleep(500)
            xbmc.executebuiltin(('XBMC.Extract("%s","%s")' % (local_tmp_file, tempdir,)).encode('utf-8'), True)

        episode_pattern = None
        if episode != '':
            episode_pattern = re.compile(get_episode_pattern(episode), re.IGNORECASE)

        for dir in xbmcvfs.listdir(tempdir)[0]:
            for file in xbmcvfs.listdir(os.path.join(tempdir, dir))[1]:
                if os.path.splitext(file)[1] in exts:
                    log(__name__, 'match '+episode+' '+file)
                    if episode_pattern and not episode_pattern.search(file):
                        continue
                    log(__name__, "=== returning subtitle file %s" % file)
                    subtitle_list.append(os.path.join(tempdir, dir, file))

        for file in xbmcvfs.listdir(tempdir)[1]:
            if os.path.splitext(file)[1] in exts:
                log(__name__, 'match '+episode+' '+file)
                if episode_pattern and not episode_pattern.search(file):
                    continue
                log(__name__, "=== returning subtitle file %s" % file)
                subtitle_list.append(os.path.join(tempdir, file))

        if len(subtitle_list) == 0:
            if episode:
                _xbmc_notification(32002)
            else:
                _xbmc_notification(32003)

    return subtitle_list


def normalizeString(str):
    return unicodedata.normalize(
        'NFKD', unicode(unicode(str, 'utf-8'))
    ).encode('ascii', 'ignore')


def get_params():
    param = {}
    paramstring = sys.argv[2]
    if len(paramstring) >= 2:
        params = paramstring
        cleanedparams = params.replace('?', '')
        if (params[len(params) - 1] == '/'):
            params = params[0:len(params) - 2]
        pairsofparams = cleanedparams.split('&')
        param = {}
        for i in range(len(pairsofparams)):
            splitparams = pairsofparams[i].split('=')
            if (len(splitparams)) == 2:
                param[splitparams[0]] = splitparams[1]

    return param


params = get_params()

if params['action'] == 'search' or params['action'] == 'manualsearch':
    item = {}
    item['temp'] = False
    item['rar'] = False
    item['mansearch'] = False
    item['year'] = xbmc.getInfoLabel("VideoPlayer.Year")  # Year
    item['season'] = str(xbmc.getInfoLabel("VideoPlayer.Season"))  # Season
    item['episode'] = str(xbmc.getInfoLabel("VideoPlayer.Episode"))  # Episode
    item['tvshow'] = normalizeString(xbmc.getInfoLabel("VideoPlayer.TVshowtitle"))  # Show
    item['title'] = normalizeString(xbmc.getInfoLabel("VideoPlayer.OriginalTitle"))  # try to get original title
    item['file_original_path'] = urllib.unquote(xbmc.Player().getPlayingFile().decode('utf-8'))  # Full path
    item['3let_language'] = []
    PreferredSub = params.get('preferredlanguage')

    if 'searchstring' in params:
        item['mansearch'] = True
        item['mansearchstr'] = params['searchstring']

    if 'languages' in params:
        for lang in urllib.unquote(params['languages']).decode('utf-8').split(","):
            item['3let_language'].append(xbmc.convertLanguage(lang, xbmc.ISO_639_2))

    if item['title'] == "":
        item['title'] = normalizeString(xbmc.getInfoLabel("VideoPlayer.Title"))  # no original title, get just Title

    if item['episode'].lower().find("s") > -1:  # Check if season is "Special"
        item['season'] = "0"  #
        item['episode'] = item['episode'][-1:]

    if item['file_original_path'].find("http") > -1:
        item['temp'] = True

    elif item['file_original_path'].find("rar://") > -1:
        item['rar'] = True
        item['file_original_path'] = os.path.dirname(item['file_original_path'][6:])

    elif item['file_original_path'].find("stack://") > -1:
        stackPath = item['file_original_path'].split(" , ")
        item['file_original_path'] = stackPath[0][8:]

    search(item)

elif params['action'] == 'download':
    # we pickup all our arguments sent from def Search()
    if 'episode' in params:
        subs = download(params["link"], params["episode"])
    else:
        subs = download(params["link"])
    # we can return more than one subtitle for multi CD versions, for now we are still working out how to handle that
    # in XBMC core
    for sub in subs:
        listitem = xbmcgui.ListItem(label=sub)
        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=sub, listitem=listitem, isFolder=False)

xbmcplugin.endOfDirectory(int(sys.argv[1]))  # send end of directory to XBMC
  
